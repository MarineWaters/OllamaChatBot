from bs4 import BeautifulSoup
import requests
import unicodedata
import dateparser
from datetime import datetime, timedelta


def parse_newest_pages(stop_titles=None):
    if stop_titles is None:
        stop_titles = set()
    parsed_docs = []
    i = 1
    while True:
        print(f'page {i}\n')
        url = f'https://smart-lab.ru/news/list/page{i}/'
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        all_news = soup.find_all("div", {'class': 'inside'})
        if not all_news:
            break

        for news_entry in all_news:
            article_url = 'https://smart-lab.ru' + news_entry.find('a')['href']
            response = requests.get(article_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            title = unicodedata.normalize("NFKC", soup.find("h1").find("span").get_text(strip=True))
            if title in stop_titles:
                return parsed_docs

            content_div = soup.find("div", {'class': 'topic'}).find("div", {'class': 'content'})
            for tag in content_div.find_all('a'):
                tag.extract()
            content = unicodedata.normalize("NFKC", content_div.get_text(strip=True))
            content = content.replace("Источник:", "")
            
            date = dateparser.parse(soup.find("li", {'class': 'date'}).get_text(strip=True))
            
            parsed_docs.append({"title": title, "content": content, "date": date, "source": article_url})
        i += 1
    return parsed_docs  

def parse_valuables():
    tickers = [("💲Доллар: ",15),("💶Евро: ",17),("🧧Юань: ",54)]
    tickers2 = [("💰Золото: ","GCUSD"),("🛢️ Нефть: ","BZUSD"),("🪙 Биткоин: ","BTCUSD")]
    valuables = "Курс ЦБ:\n"
    for t in tickers:
        response = requests.get(f'https://www.cbr.ru/currency_base/daily/')
        response.raise_for_status()
        valuables += f"{t[0]}₽{BeautifulSoup(response.text, 'lxml').find("table", {'class': 'data'}).find_all('tr')[t[1]].find_all('td')[4].get_text(strip=True)}\n"
    valuables+="\nКурс на 07:00 по МСК:\n"
    for t in tickers2:
        response = requests.get(f'https://smart-lab.ru/')
        response.raise_for_status()
        valuables += f"{t[0]}${BeautifulSoup(response.text, 'lxml').find("tr", {'tkr': t[1]}).find_all('td')[1].get_text()}\n"
    parsed_prices = [{"prices": valuables, "date": datetime.now()-timedelta(days=1)}]
    return parsed_prices