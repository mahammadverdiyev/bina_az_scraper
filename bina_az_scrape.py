import functools
import os.path

import requests
from bs4 import BeautifulSoup
import pymysql
import threading
import time
from functools import wraps

connection = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database=''
)


def synchronized(wrapped):
    lock = threading.Lock()
    print(lock, id(lock))

    @functools.wraps(wrapped)
    def _wrap(*args, **kwargs):
        with lock:
            # print("Calling '%s' with Lock %s from thread %s [%s]"
            #       % (wrapped.__name__, id(lock),
            #          threading.current_thread().name, time.time()))
            result = wrapped(*args, **kwargs)
            # print("Done '%s' with Lock %s from thread %s [%s]"
            #       % (wrapped.__name__, id(lock),
            #          threading.current_thread().name, time.time()))
            return result

    return _wrap


# pymysql is not thread safe, so I took some precautions
@synchronized
def insert_to_table(all_data: list, conn, table):
    cols = ['elan_id', 'kateqoriya', 'mertebe', 'otaq_say', 'sahe', 'qiymet', 'kvm_qiymet', 'adres', 'baxis_say',
            'kupca', 'satici', 'ipoteka', 'elan_basliq',
            'info']
    to = ','.join(cols)
    insert_sql = f"insert into {table}  ({to}) values({','.join(['%s' for i in range(len(cols))])})"

    for data in all_data:
        values = [data[col] for col in cols]
        with conn.cursor() as cursor:
            cursor.execute(insert_sql, values)
            connection.commit()


website = 'https://bina.az'

# 1180

headers = {
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:104.0) Gecko/20100101 Firefox/104.0"}

BASE_URL = 'https://bina.az/baki/alqi-satqi/menziller?page='


def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f'Total time: {total_time:.3f} seconds')
        return result

    return timeit_wrapper


def fetch_inner_data(url: str):
    parameters = {'İpoteka': 'yoxdur'}
    inner_response = requests.get(url, headers=headers)
    inner_soup = BeautifulSoup(inner_response.content, 'lxml')

    try:
        # qiymet
        price_cur = inner_soup.find('span', class_='price-cur').text
        price = inner_soup.find('span', class_='price-val').text
        parameters['qiymet'] = price + ' ' + price_cur

        # kvm_qiymet
        price_sqft = inner_soup.find('div', class_='unit-price').text
        parameters['kvm_qiymet'] = price_sqft

        # elan basliq
        title = inner_soup.find('div', class_='services-container').find('h1').text
        parameters['elan_basliq'] = title

        # adres
        address = title.split(',')[-1].strip()
        parameters['adres'] = address

        # parametrlər
        category_table = inner_soup.find('table', class_='parameters')
        params = category_table.find_all('tr')
        for param in params:
            tds = param.find_all('td')
            parameters[tds[0].text] = tds[1].text

        # satici
        contacts_tag = inner_soup.find('section', class_='contacts')
        seller = contacts_tag.find('div', class_='name').findChild().previous
        parameters['satici'] = seller

        # elan id, baxis_sayi
        post_infos = inner_soup.find('div', class_='item_info').findChildren()
        post_id = post_infos[0].text.split(' ')[2]
        view_count = post_infos[1].text.split(' ')[2]
        parameters['elan_id'] = post_id
        parameters['baxis_say'] = view_count

        # info
        info = inner_soup.find('article').text.replace('\n', ' ')
        parameters['info'] = info
    except Exception:
        return None
    new_param_names = {'Kateqoriya': 'kateqoriya', 'Kupça': 'kupca', 'Mərtəbə': 'mertebe', 'Otaq sayı': 'otaq_say',
                       'Sahə': 'sahe', 'İpoteka': 'ipoteka'}

    for old_name, new_name in new_param_names.items():
        parameters[new_name] = parameters.pop(old_name)

    return parameters


@synchronized
def write_to_file(page):
    with open('page_error.txt', mode='a') as f:
        f.write(str(page) + '\n')


@timeit
def start_scraping(start, end):
    print(f"________________{start} -  {end}________________")
    for page in range(start, end):
        try:
            response = requests.get(f'{BASE_URL}{page}', headers=headers)
            soup = BeautifulSoup(response.content, 'lxml')
            outer_container = soup.find('div', id='js-items-search').find_all('div', class_='items_list')[-1]
            containers = outer_container.find_all('div', class_='items-i')
            alL_data = []

            for container in containers:
                url_tag = container.find_next('a')
                url = url_tag.get('href')
                inner_data = fetch_inner_data(f'{website}{url}')
                if inner_data is None:
                    continue
                alL_data.append(inner_data)
                print(f"Page - {page}, Url - {website}{url}")
                # time.sleep(random.randint(1, 5))
            insert_to_table(alL_data, connection, 'bina_db')
        except Exception as e:
            write_to_file(page)
            print(f'Exception in page = {page}')
            # print(e)
            return


all_threads = []

THREAD_COUNT = 12
PAGES = 1140
PAGES_PER_THREAD = PAGES // THREAD_COUNT

page_counter = 1


def get_default_pages() -> list:
    page_counter = 1
    pages = []
    for i in range(THREAD_COUNT):
        pages.append(page_counter)
        page_counter += PAGES_PER_THREAD
    return pages


def write_defaults():
    with open('page_error.txt', mode='w') as f:
        pages = get_default_pages()
        for page in pages:
            f.write(f'{page}\n')


if not os.path.exists('page_error.txt'):
    write_defaults()

with open('page_error.txt', mode='r') as f:
    lines = f.readlines()
    lines = [int(i) for i in lines]
    if len(lines) == 0:
        write_defaults()


print(lines)

open('page_error.txt', 'w').close()

lines = sorted(lines)

for i in range(THREAD_COUNT):
    curr_page = lines[i]
    thread = threading.Thread(target=start_scraping, args=(curr_page, page_counter + PAGES_PER_THREAD,))
    page_counter += PAGES_PER_THREAD
    all_threads.append(thread)

for thread in all_threads:
    thread.start()

for thread in all_threads:
    thread.join()
