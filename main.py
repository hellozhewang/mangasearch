import requests
import pickle
import os.path
import time
import random
from collections import defaultdict
from datetime import datetime
import sys


def get_file_age_seconds(path):

    # Get the modification time of the file
    mod_time = os.path.getmtime(path)

    # Calculate the age of the file in seconds
    age = time.time() - mod_time

    # Print the age of the file
    print(f'Cache age secs {age}')
    return age


def get_bearer_token():
    # user_id = 54455593497
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


def load_cache(cache_path, time_limit_secs=sys.maxsize):
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
    cache_path = '/home/zzwang/mangasearch/cache.pickle'
    results = load_cache(cache_path, 300)
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
               #"list": "102", # RWC
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

    save_cache(cache_path, results)

    print(f'Actual Hits: {len(results)}')
    return results


def get_rating(token, series_id, cache):
    if series_id in cache and (time.time() - cache[series_id]['cache_timestamp']) <= 3600 * 24 * 10:
        return cache[series_id]
    url = f"https://api.mangaupdates.com/v1/series/{series_id}/ratingrainbow"
    resp = get(token, url)
    if resp:
        cache[series_id] = resp
        cache[series_id]['cache_timestamp'] = time.time(
        ) + random.randint(3600 * 24 * 15, 3600 * 24 * 30)
    return resp


def get_series(token, series_id, cache):
    if series_id in cache and (time.time() - cache[series_id]['cache_timestamp']) <= 3600 * 24 * 10:
        return cache[series_id]
    url = f"https://api.mangaupdates.com/v1/series/{series_id}"
    resp = get(token, url)
    if resp:
        cache[series_id] = resp
        cache[series_id]['cache_timestamp'] = time.time(
        ) + random.randint(3600 * 24 * 5, 3600 * 24 * 15)
    return resp


def get(token, url):
    headers = {'Authorization': 'Bearer ' + token}
    resp = ''
    try:
        resp = requests.get(url, headers=headers)
        json = resp.json()
        time.sleep(.75)
    except:
        print(f'Unable to get {url} \n {resp}')
        return None
    return json


def filter_record(token, results):
    records = []

    series_cache_path = '/home/zzwang/mangasearch/series_cache.pickle'
    series_cache = load_cache(series_cache_path)
    if not series_cache:
        series_cache = {}
    print(f'Series cache len: {len(series_cache)}')

    rating_cache_path = '/home/zzwang/mangasearch/rating_cache.pickle'
    rating_cache = load_cache(rating_cache_path)
    if not rating_cache:
        rating_cache = {}
    print(f'Rating cache len: {len(rating_cache)}')

    i = 0
    for record in results:
        i += 1
        debug = {}
        id = record['series_id']
        year = int(record["year"][0:4]) if record["year"] else 0
        genres = set([v["genre"] for v in record["genres"]])
        z_rating = record['bayesian_rating']
        votes = record['rating_votes']
        rating = get_rating(token, id, rating_cache)
        avg_rating = rating['average_rating'] if rating and 'average_rating' in rating else 0
        record['average_rating'] = avg_rating

        if z_rating >= 8.00:
            z_rating += .5
            debug['8Club'] = .5

        if votes < 30:
            hype_gravity = 17
            global_mean = 6.40
            
            # Calculate the aggressive "Hype Score"
            hype_score = (votes * avg_rating + hype_gravity * global_mean) / (votes + hype_gravity)
            
            # The 'mod' is the difference between the Hype Score and the Conservative Score
            # Example: Hype says 8.0, Conservative says 6.5 -> Bonus is +1.5
            mod = hype_score - record['bayesian_rating']
            
            # Sanity check: Ensure we don't accidentally punish high-performing stuff 
            # (though mathematically unlikely with this formula)
            mod = max(0, mod)
            
            z_rating += mod
            debug['Trending'] = mod

        # adjust for old
        year_limit = 2020
        if year < year_limit:
            mod = (year_limit - year) / 9
            mod = min(mod, 2.5)
            z_rating -= mod
            debug['Year'] = -mod

        # adjust for genres
        genre_weights = {
            'Seinen': 0.10,
            'Shounen': 0.025,
            'Josei': 0.05,
            'Adult': 0.025,
            'Shoujo': -0.10,
            'Harem' : -0.10,
        }

        for genre, weight in genre_weights.items():
            if genre in genres:
                z_rating += weight
                debug[genre] = weight

        series = get_series(token, id, series_cache)
        if series:
            categories = {category['category']: category['votes_plus']
                          for category in series['categories']}

            if 'Fast Romance' in categories:
                mod = .02 + .02 * categories['Fast Romance']
                mod = min(mod, .05)
                z_rating += mod
                debug['FastRomance'] = mod

            if 'Beautiful Artwork' in categories:
                mod = .01 + .01 * categories['Beautiful Artwork']
                mod = min(mod, .05)
                z_rating += mod
                debug['Beautiful Artwork'] = mod

            if 'Married Couple' in categories or 'Established Couple' in categories:
                mod = .02
                if 'Married Couple' in categories:
                    mod += .02 * categories['Married Couple']
                if 'Established Couple' in categories:
                    mod += .02 * categories['Established Couple']
                mod = min(mod, .08)
                z_rating += mod
                debug['Couple'] = mod

            if series['completed'] or ('Complete' in str(series['status']) and 'Ongoing' not in str(series['status'])):
                mod = .125
                z_rating += mod
                debug['Completed'] = mod

            record['status'] = series['status']
        else:
            record['status'] = ''

        record['z_rating'] = '%.3f' % (z_rating)
        record['debug'] = {k: '%.3f' % v for k, v in debug.items()}
        records.append(record)
        if i % 10 == 0:
            print(f'Record counter: {i}')
        if i % 250 == 0:
            save_cache(series_cache_path, series_cache)
            save_cache(rating_cache_path, rating_cache)

    save_cache(series_cache_path, series_cache)
    save_cache(rating_cache_path, rating_cache)
    z_rating = max(z_rating, record['bayesian_rating'])
    records = sorted(records, key=lambda x: (
        x['z_rating'], x['average_rating'], x['bayesian_rating']), reverse=True)
    return records[0:min(150, len(results))]


def write(records):
    print(f'Rendering: {len(records)}')
    # Get the keys from the dictionary to use as column headers
    file = '/home/zzwang/mangasearch/src/index.html'
    with open(file, 'w') as f:
        # Write the beginning of the HTML file
        f.write('<html>\n<head><link rel="icon" href="https://pics.freeicons.io/uploads/icons/png/17101267261557740324-512.png" >\n<style>\n')
        f.write(
            'table, th, td {\nborder: 1px solid black;\nborder-collapse: collapse;\n}\n')
        f.write(
            'th, td {\npadding: 5px;\ntext-align: left;\nborder-style: dotted;\n}\n')
        f.write('</style>\n</head>\n<body>\n')
        f.write(
            f'<p> Last updated: {datetime.now().strftime("%m/%d/%Y %H:%M:%S")}</p>')
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
            f.write(
                f'<td><a target="_blank" href="{row["url"]}">link</a></td>')
            f.write(f'<td>{ row["bayesian_rating"] }</td>')
            f.write(f'<td>{ row["average_rating"] }</td>')
            f.write(f'<td><b>{ row["z_rating"] }</b></td>')
            f.write(f'<td width=10%><b>{ row["debug"] }</b></td>')
            f.write(
                f'<td><a target="_blank" href="{"https://www.google.com/search?q=" + "read+" + row["title"].replace(" ", "+")}">google</a><br/>'
                f'<a target="_blank" href="{"https://duckduckgo.com/?q=" + "read+" + row["title"].replace(" ", "+")}">duck</a><br/>'
                f'<a target="_blank" href="{"https://yandex.com/search/?text=" + "read+" + row["title"].replace(" ", "+")}">yandex</a> </td>')
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
