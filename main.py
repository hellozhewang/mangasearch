import requests
import pickle
import os.path
import time
import random
from collections import defaultdict


def get_file_age_seconds(path):

    # Get the modification time of the file
    mod_time = os.path.getmtime(path)

    # Calculate the age of the file in seconds
    age = time.time() - mod_time

    # Print the age of the file
    print(f'Cache age secs {age}')
    return age


def get_bearer_token():
    url = "https://api.mangaupdates.com/v1/account/login"
    payload = {"username": "cloakedshield", "password": "Lythander5!"}

    # Make a POST request to the API endpoint with the authorization header and payload
    response = requests.put(url, json=payload).json()

    if response['status'] == 'success':
        # If successful, return the response content as a JSON object
        return response['context']['session_token']
    else:
        # If not successful, raise an exception with the response status code and reason
        raise Exception(f'Error getting token: {response}')


def load_cache(cache_path, time_limit_secs):
    if os.path.isfile(cache_path) and get_file_age_seconds(cache_path) < time_limit_secs:
        with open(cache_path, 'rb') as handle:
            results = pickle.load(handle)
            print(f'Loaded hits from cache: {len(results)}')
            return results
    return None


def save_cache(cache_path, data):
    with open(cache_path, 'wb') as handle:
        pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)


def query(token, genres, exclude, limit):
    cache_path = '/Users/zzwang/Documents/MangaScript/cache.pickle'
    results = load_cache(cache_path, 3600)
    if results:
        return results
    else:
        results = []

    url = "https://api.mangaupdates.com/v1/series/search"
    # Set the authorization header with the bearer token
    headers = {'Authorization': 'Bearer ' + token}
    payload = {"page": 1,
               "perpage": 100,
               "include_rank_metadata": False,
               "genre": genres,
               "list": "none",
               "filter": "no_oneshots",
               "type": ["Manga", "Manhwa", "Manhua"],
               "exclude_genre": exclude,
               "orderby": "rating"}

    # Make a POST request to the API endpoint with the authorization header and payload
    response = requests.post(url, headers=headers, json=payload).json()
    total = response['total_hits']
    print(f'Total Hits: {total}')
    page = 1
    score = 10

    while len(results) < total and score >= limit:
        response = requests.post(url, headers=headers, json=payload).json()
        for r in response['results']:
            if 'record' not in r:
                print(f'Bad record: {r}')
                continue
            results.append(r['record'])
        score = results[-1]['bayesian_rating']
        page += 1
        payload['page'] = page
        print(f"Processed: {len(results)}")

    with open(cache_path, 'wb') as handle:
        pickle.dump(results, handle, protocol=pickle.HIGHEST_PROTOCOL)

    print(f'Actual Hits: {len(results)}')
    return results


def get_series(token, series_id, cache):
    if series_id in cache and (time.time() - cache[series_id]['cache_timestamp']) <= 3600 * 24 * 10:
        return cache[series_id]
    url = f"https://api.mangaupdates.com/v1/series/{series_id}"
    headers = {'Authorization': 'Bearer ' + token}
    try:
        resp = requests.get(url, headers=headers)
        json = resp.json()
        time.sleep(.5)
    except:
        print(f'Unable to get series {series_id} \n {resp}')
        return None
    cache[series_id] = json
    cache[series_id]['cache_timestamp'] = time.time() + random.randint(1800, 3600 * 24 * 5)
    return cache[series_id]


def filter_record(token, results):
    records = []

    def calc_vote_mod(votes):
        return .004*votes + .0006*pow(votes, 2) - .0000128*pow(votes, 3) + .000000064*pow(votes, 4)

    cache_path = '/Users/zzwang/Documents/MangaScript/series_cache.pickle'
    cache = load_cache(cache_path, 3600 * 24 * 9999999)
    if not cache:
        cache = {}
    print(f'Series cache len: {len(cache)}')
    i = 0
    for record in results:
        i += 1
        debug = {}
        id = record['series_id']
        year = int(record["year"][0:4]) if record["year"] else 0
        genres = [v["genre"] for v in record["genres"]]
        z_rating = record['bayesian_rating']
        votes = record['rating_votes']
        # adjust for old
        year_limit = 2014
        if year <= year_limit:
            mod = (year_limit - year) / 12
            min(mod, 1.5)
            z_rating -= mod
            debug['Year'] = -mod

        if votes <= 100:
            mod = calc_vote_mod(votes)
            if year <= year_limit:
                mod -= (year_limit - year) / 12
            mod = max(0, mod)
            z_rating += mod
            debug['Votes'] = mod

        # adjust for genres
        if 'Seinen' in genres:
            z_rating += .35
            debug['Seinen'] = .35
        if 'Shounen' in genres:
            z_rating += .25
            debug['Shounen'] = .25
        if 'Josei' in genres:
            z_rating += .10
            debug['Josei'] = .10
        if 'Adult' in genres:
            z_rating += .10
            debug['Adult'] = .10

        series = get_series(token, id, cache)
        if series:
            categories = {category['category']: category['votes_plus']
                        for category in series['categories']}

            if 'Fast Romance' in categories:
                mod = .05 + .02 * categories['Fast Romance']
                mod = min(mod, .1)
                z_rating += mod
                debug['FastRomance'] = mod

            if 'Beautiful Artwork' in categories:
                mod = .06 + .04 * categories['Beautiful Artwork']
                mod = min(mod, .2)
                z_rating += mod
                debug['Beautiful Artwork'] = mod

            if 'Married Couple' in categories or 'Established Couple' in categories:
                mod = .05
                if 'Married Couple' in categories:
                    mod += .02 * categories['Married Couple']
                if 'Established Couple' in categories:
                    mod += .02 * categories['Established Couple']
                mod = min(mod, .1)
                z_rating += mod
                debug['Couple'] = mod
            
            record = series
        else:
            record['status'] = ''

        record['z_rating'] = '%.3f' % (z_rating)
        record['debug'] = {k: '%.3f' % v for k, v in debug.items()}
        records.append(record)
        if i % 10 == 0:
            print(f'Record counter: {i}')

    save_cache(cache_path, cache)
    records = sorted(records, key=lambda x: x['z_rating'], reverse=True)
    return records[0:min(250, len(results))]

        



def write(records):
    print(f'Rendering: {len(records)}')
    # Get the keys from the dictionary to use as column headers
    file = '/Users/zzwang/Documents/MangaScript/out.html'
    with open(file, 'w') as f:
        # Write the beginning of the HTML file
        f.write('<html>\n<head>\n<style>\n')
        f.write(
            'table, th, td {\nborder: 1px solid black;\nborder-collapse: collapse;\n}\n')
        f.write(
            'th, td {\npadding: 5px;\ntext-align: left;\nborder-style: dotted;\n}\n')
        f.write('</style>\n</head>\n<body>\n')

        # Generate the table
        f.write('<table>\n<tr>')
        f.write('</tr>\n')
        i = 1
        for row in records:
            f.write('<tr>')
            f.write(f'<td>{ i }</td>')
            f.write(f'<td width=15%>{ row["title"] }</td>')
            f.write(f'<td><img src="{row["image"]["url"]["thumb"]}"></td>')
            f.write(f'<td>{ row["year"] }</td>')
            f.write(
                f'<td width=15%>{ ",".join(v["genre"] for v in row["genres"]) }</td>')
            f.write(f'<td width=15%>{ row["status"] }</td>')
            f.write(f'<td>{ row["rating_votes"] }</td>')
            f.write(f'<td><a href="{row["url"]}">link</a></td>')
            f.write(f'<td>{ row["bayesian_rating"] }</td>')
            f.write(f'<td><b>{ row["z_rating"] }</b></td>')
            f.write(f'<td width=10%><b>{ row["debug"] }</b></td>')
            f.write('</tr>\n')
            i += 1
        f.write('</table>\n')

        # Write the end of the HTML file
        f.write('</body>\n</html>')


def main():
    genres = ['Romance']
    exclude = ["Shotacon", "Shoujo Ai", "Shounen Ai", "Yaoi", "Yuri", "Hentai"]
    limit = 6.8
    token = get_bearer_token()
    results = query(token, genres, exclude, limit)
    records = filter_record(token, results)
    write(records)


if __name__ == "__main__":
    main()
