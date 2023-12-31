#!/usr/bin/env python
""" Andrey S

    This script gets vacancies from hh.ru
    according to the filtering rules 
    and saves them in the sqlite database
    
    Education project
"""
import argparse
#TODO: import typing 

import aiohttp
import asyncio
#from aiolimiter import AsyncLimiter
from tqdm import tqdm
import sqlite3
from bs4 import BeautifulSoup
import json

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import  Column, Integer, String

import logging.config


LOG_CONFIG = {
    "version": 1,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "ERROR"
        },
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "DEBUG",
            "when": "D",
            "backupCount": 0,
            "filename": "./ex_2_1.log"
        }
    },
    "loggers": {
        "__main__": {
            "handlers": ["console", "file"]
        },
        "": {
            "handlers": ["file"],
            "propagate": True
        }
    }
}

logging.config.dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)

CONCURENT_LIMIT = 3 #3 connections simultaneously
#limiter = AsyncLimiter(10, 20) #only 10 connections by 20 seconds

"""
    Structures for database
"""
class hh2(DeclarativeBase): pass
class vacancies_db(hh2):
    __tablename__ = "vacancies"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String) 
    position = Column(String) 
    job_description = Column(String)
    key_skills= Column(String)
 

headers = {'User-agent': 'Mozilla/4.0'}

"""
    params for get query
"""
params = { 'no_magic' : 'false',
 'L_save_area' : 'false',
 'text' : 'python middle developer',
 'search_field' : 'name',
 'excluded_text' : '',
 'currency_code' : 'RUR',
 'order_by' : 'relevance',
 'search_period' : '0'}
 
 
"""
    get information for single vacancy and past it to queue
""" 
async def get_vacancy_detail(session, records_queue, url, method):
    try:
        r = await session.get(url)
        r.raise_for_status()
        
        resp_text=await r.text()
        if method=='web':
            soup = BeautifulSoup(resp_text, 'html.parser')
            vacancy=json.loads(soup.find('template', id='HH-Lux-InitialState').string)
            # .encode().decode('unicode_escape'))
            if ("keySkills" in vacancy["vacancyView"] and vacancy["vacancyView"]["keySkills"]):
                skills=json.dumps(vacancy["vacancyView"]["keySkills"]["keySkill"]).encode().decode('unicode-escape')
            else:
                skills=None
            record_put = {
                "company_name": vacancy["vacancyView"]["company"]["visibleName"],
                "position": vacancy["vacancyView"]["name"],
                "job_description": vacancy["vacancyView"]["description"],
                "key_skills": skills
            }
        else:
            vacancy=json.loads(resp_text)
            if (len(vacancy["key_skills"])):
                skills=[]
                for skill_r in vacancy["key_skills"]:
                    skills.append(skill_r["name"])
            else:
                skills=None
            
            record_put = {
                "company_name": vacancy["employer"]["name"],
                "position": vacancy["name"],
                "job_description": vacancy["description"],
                "key_skills": json.dumps(skills)
            }
            
        await records_queue.put(record_put)
    except (aiohttp.ServerDisconnectedError,aiohttp.ClientResponseError,aiohttp.ClientConnectorError) as e:
        logger.error(f'Cannot get vacancy url {url}. Stats code: {e.status}')
        #raise
    except (json.JSONDecodeError, KeyError):
        logger.error(f'Cannot parse JSON from {url}')
        #raise
    except Exception as error:
        logger.error(f'Some error when get data from {url}', exc_info=True)

"""
    get web url of vacancy from queue
    n (CONCURENT_LIMIT) workers runs together
""" 

async def get_worker(queue, records_queue, session, pbar, method):
    while True:
        url = await queue.get()

        #async with limiter:
        await get_vacancy_detail(session, records_queue, url, method)
        queue.task_done()
        pbar.update()
    return

"""
    create empty databse
""" 
def prepare_database():
    try:
        engine=create_engine(f"sqlite:///{args.database.name}")
        hh2.metadata.drop_all(bind=engine)
        hh2.metadata.create_all(bind=engine)
    except sqlite3.Error:
        logger.error("Exception sqlite3 occurred", exc_info=True)
    return engine
    
"""
    main process
    read list of vacancies, put it to queue_1
    run n (CONCURENT_LIMIT) tasks for working with queue_1
    put result from queue_2 to database   
"""     
async def main(method):
    con = aiohttp.TCPConnector(limit=CONCURENT_LIMIT)
    async with aiohttp.ClientSession(connector=con) as session:
        try:
            engine=prepare_database()
            queue = asyncio.Queue()
            records_queue = asyncio.Queue()
            #logger.info
            print('Get list of vacancies by filter...', end=' ' )
            if method=='web':
                start_url='https://krasnodar.hh.ru/search/vacancy'
            else:
                start_url='https://api.hh.ru/vacancies'
            
            async with session.get(start_url, headers=headers, params=params, raise_for_status=True) as r:
                #r.raise_for_status()
                resp_text=await r.text()
                if method=='web':
                    soup = BeautifulSoup(resp_text, 'html.parser')
                    vacancy_raw = soup.find_all(class_="serp-item")
                    vacancies=json.loads(soup.find('noindex').string)["vacancySearchResult"]["vacancies"]
                    
                    for vacancy in vacancies:
                        queue.put_nowait(vacancy["links"]["mobile"])
                else:
                    vacancies=json.loads(resp_text)
                    for vacancy in vacancies["items"]:
                        queue.put_nowait(vacancy["url"])
                print(f'Done. Found {queue.qsize()} vacancies')    
                print('Get description for every vacancy')    
                pbar=tqdm(total=queue.qsize(), unit='vacancies', leave=False)
                tasks = [
                    asyncio.create_task(get_worker(queue, records_queue, session, pbar, method))
                    for idx in range(CONCURENT_LIMIT)
                ]
                #wait
                await queue.join()
                
                #all done. now cencel running tasks
                for task in tasks:
                    task.cancel()
                #wait
                await asyncio.gather(*tasks, return_exceptions=True)
            print('\nInsert data to database...', end=' ' )    
            with Session(autoflush=False, bind=engine) as db:
                records = []
                while not records_queue.empty():
                    #get_nowait
                    records.append(await records_queue.get())
                try:
                    db.execute(insert(vacancies_db), records)
                    db.commit()
                except sqlite3.Error:
                    logger.error("Exception sqlite3 occurred", exc_info=True)
            print('All Done!')
        except (aiohttp.ServerDisconnectedError,aiohttp.ClientResponseError,aiohttp.ClientConnectorError) as e:
            logger.error(f'Cannot get list of vacancies. Stats code: {e.status}')
        except (json.JSONDecodeError, KeyError):
            logger.error(f'Cannot parse list of vacancies')

            
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gets vacancies from hh.ru according to the filtering rules and saves them in the database')
    parser.add_argument('-m', '--method', choices=['web', 'api'], default='web', help='Choise method for getting information web-site scraping or rest-api')
    parser.add_argument("-d", '--database', help="Database file location, created if not exists",  type=argparse.FileType('w'), default="hh2.db")
    parser.add_argument("-f", '--filter', help="Filter for search vacncies. Default 'python middle developer'", default="python middle developer")
    parser.add_argument("-l", '--limit', help="Limit number of vacancies on page", type=int, default=20)
    args = parser.parse_args()
    
    params['text']=args.filter
    
    if args.method=='web':
        params['items_on_page']=args.limit
        
    else:
        params['per_page']=args.limit
        #asyncio.run(api())
    asyncio.run(main(args.method))
    

