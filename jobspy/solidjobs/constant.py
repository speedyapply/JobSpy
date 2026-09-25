# Headers for SOLID.Jobs public API requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Public API base url (no auth/key required, see https://solid.jobs/api-ofert-pracy)
api_url = "https://solid.jobs/public-api/offers"

# Campaign identifier required by the public API (lowercase, digits, dashes; max 64 chars)
default_campaign = "jobspy"

# Job categories (divisions) supported by the API, used as the path segment
divisions = [
    "IT",
    "Engineering",
    "Marketing",
    "Sales",
    "HR",
    "Logistics",
    "Finances",
    "Other",
]

# Max page size accepted by the API
max_page_size = 500
