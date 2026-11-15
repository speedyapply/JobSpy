from jobspy.model import CompensationInterval

base_url = "https://www.infojobs.net"
search_url = f"{base_url}/webapp/offers/search"
spain_id = 17
delay_env = "INFOJOBS_DELAY"
default_delay = (3.0, 6.0)

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "es-ES,es;q=0.9",
    "referer": f"{base_url}/ofertas-trabajo",
}

# teleworkingIds: 1 Presencial, 2 Solo teletrabajo, 3 Híbrido, 4 Sin especificar
remote_id = 2
remote_label = "Solo teletrabajo"

# hours_old up to a week asks the site for the last week; the rest is filtered here
week_hours = 168
last_week = "_7_DAYS"

pay_intervals = {
    "YEAR": CompensationInterval.YEARLY,
    "MONTH": CompensationInterval.MONTHLY,
    "WEEK": CompensationInterval.WEEKLY,
    "DAY": CompensationInterval.DAILY,
    "HOUR": CompensationInterval.HOURLY,
}

# provinceIds, keyed as the site's /ofertas-trabajo/<province> links write them
provinces = {
    "a-coruna": 28,
    "alava-araba": 2,
    "albacete": 3,
    "alicante-alacant": 4,
    "almeria": 5,
    "asturias": 6,
    "avila": 7,
    "badajoz": 8,
    "barcelona": 9,
    "burgos": 10,
    "caceres": 11,
    "cadiz": 12,
    "cantabria": 13,
    "castellon-castello": 14,
    "ceuta": 15,
    "ciudad-real": 16,
    "cordoba": 17,
    "cuenca": 18,
    "girona": 19,
    "granada": 21,
    "guadalajara": 22,
    "guipuzcoa-gipuzkoa": 23,
    "huelva": 24,
    "huesca": 25,
    "islas-baleares-illes-balears": 26,
    "jaen": 27,
    "la-rioja": 29,
    "las-palmas": 20,
    "leon": 30,
    "lleida": 31,
    "lugo": 32,
    "madrid": 33,
    "malaga": 34,
    "melilla": 35,
    "murcia": 36,
    "navarra": 37,
    "ourense": 38,
    "palencia": 39,
    "pontevedra": 40,
    "salamanca": 41,
    "santa-cruz-de-tenerife": 46,
    "segovia": 42,
    "sevilla": 43,
    "soria": 44,
    "tarragona": 45,
    "teruel": 47,
    "toledo": 48,
    "valencia-valencia": 49,
    "valladolid": 50,
    "vizcaya-bizkaia": 51,
    "zamora": 52,
    "zaragoza": 53,
}

# other spellings of a province -> its key above
province_aliases = {
    "coruna": "a-coruna",
    "la-coruna": "a-coruna",
    "alava": "alava-araba",
    "araba": "alava-araba",
    "alicante": "alicante-alacant",
    "alacant": "alicante-alacant",
    "castellon": "castellon-castello",
    "castello": "castellon-castello",
    "guipuzcoa": "guipuzcoa-gipuzkoa",
    "gipuzkoa": "guipuzcoa-gipuzkoa",
    "baleares": "islas-baleares-illes-balears",
    "illes-balears": "islas-baleares-illes-balears",
    "islas-baleares": "islas-baleares-illes-balears",
    "mallorca": "islas-baleares-illes-balears",
    "valencia": "valencia-valencia",
    "vizcaya": "vizcaya-bizkaia",
    "bizkaia": "vizcaya-bizkaia",
    "tenerife": "santa-cruz-de-tenerife",
    "gran-canaria": "las-palmas",
}
