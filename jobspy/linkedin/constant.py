from jobspy.model import CompensationInterval

headers = {
    "authority": "www.linkedin.com",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

currencies = {"$": "USD", "CA$": "CAD", "£": "GBP", "€": "EUR", "₹": "INR"}

pay_intervals = {
    "/hr": CompensationInterval.HOURLY,
    "/mo": CompensationInterval.MONTHLY,
    "/yr": CompensationInterval.YEARLY,
}
