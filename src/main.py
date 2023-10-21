import re
from urllib.parse import urljoin
import logging

from requests_cache import CachedSession
from bs4 import BeautifulSoup
from tqdm import tqdm

from constants import BASE_DIR, MAIN_DOC_URL, PEP_DOC_URL
from configs import configure_argument_parser, configure_logging
from outputs import control_output
from utils import get_response, find_tag


def whats_new(session):
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор'), ]
    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(
        main_div, 'div', attrs={'class': 'toctree-wrapper compound'}
    )
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )

    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (version_link, h1.text, dl_text)
        )

    return results


def latest_versions(session):
    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise Exception('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус'), ]
    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        search_result = re.search(pattern, a_tag.text)
        if search_result:
            version, status = search_result.groups()
        else:
            version = a_tag.text
            status = ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    response = get_response(session, downloads_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    main_tag = find_tag(soup, 'div', attrs={'role': 'main'})
    table_tag = find_tag(main_tag, 'table', attrs={'class': 'docutils'})
    pdf_a4_tag = find_tag(
        table_tag, 'a', attrs={'href': re.compile(r'.+pdf-a4\.zip$')}
    )
    archive_url = urljoin(downloads_url, pdf_a4_tag['href'])
    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)
    with open(archive_path, 'wb') as file:
        file.write(response.content)
    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    peps_url = PEP_DOC_URL
    response = get_response(session, peps_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text, features='lxml')
    numerical_index = find_tag(
        soup, 'section', attrs={'id': 'numerical-index'}
    )
    table_body = find_tag(numerical_index, 'tbody')
    rows = table_body.find_all('tr')
    results = {
        'All': 0,
        'Active': 0,
        'Accepted': 0,
        'Deferred': 0,
        'Final': 0,
        'Provisional': 0,
        'Rejected': 0,
        'Superseded': 0,
        'Withdrawn': 0,
        'Draft': 0,
    }
    for row in rows:
        td = find_tag(row, 'td')
        title = td.abbr['title']
        status_on_title_page = title.split()[-1]
        td = td.find_next_sibling('td')
        pep_href = td.a['href']
        url = urljoin(peps_url, pep_href)
        response = get_response(session, url)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        pep_content = find_tag(soup, 'section', attrs={'id': 'pep-content'})
        main_info = find_tag(pep_content, 'dl')
        dt = find_tag(main_info, 'dt')
        while dt.text != 'Status:':
            dt = dt.find_next_sibling('dt')
        status_dd = dt.find_next_sibling('dd')
        status_on_pep_page = status_dd.abbr.text
        if status_on_pep_page != status_on_title_page:
            logging.info(
                f'\nНесовпадающие статусы: {url}\n'
                f'Статус в карточке: {status_on_pep_page}\n'
                f'Ожидаемый статус: {status_on_title_page}\n'
            )
            continue
        results[status_on_pep_page] += 1
        results['All'] += 1
    list_of_results = [('Status', 'Count'), ]
    list_of_results.extend(results.items())
    return list_of_results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')
    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')
    session = CachedSession()
    if args.clear_cache:
        session.cache.clear()
    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)
    if results:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
