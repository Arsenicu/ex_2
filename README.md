# ex_2
    This script gets vacancies from hh.ru according to the filtering rules and saves them in the sqlite database.
    Education project

![ex_2_scheme](https://github.com/Arsenicu/ex_2/blob/main/ex_2_scheme.png)

### Requirements
Python 3.10.6<br/>
aiohttp<br/>
beautifulsoup4<br/>
SQLAlchemy<br/>
tqdm<br/>
```
pip install -r requirements.txt
```

#### Options
```
  ::python ex_2_1.py --help
usage: ex_2_1.py [-h] [-m {web,api}] [-d DATABASE] [-f FILTER] [-l LIMIT]

Gets vacancies from hh.ru according to the filtering rules and saves them in
the database

optional arguments:
  -h, --help            show this help message and exit
  -m {web,api}, --method {web,api}
                        Choise method for getting information web-site scraping
                        or rest-api
  -d DATABASE, --database DATABASE
                        Database file location, created if not exists
  -f FILTER, --filter FILTER
                        Filter for search vacncies. Default 'python middle
                        developer'
  -l LIMIT, --limit LIMIT
                        Limit number of vacancies on page
```
