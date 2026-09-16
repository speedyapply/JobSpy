base_url = "https://jobsbylevel.com"

# Jobs posted in the last 7 days (documented at https://jobsbylevel.com/feeds)
recent_feed_url = f"{base_url}/feeds/jobs/recent.xml"
recent_feed_max_hours = 7 * 24

# Full catalogue, split in numbered pages; a missing page returns 404
catalogue_page_url = f"{base_url}/feeds/jobs/{{page}}.xml"
max_catalogue_pages = 100

headers = {
    "accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "user-agent": "Mozilla/5.0 (compatible; JobSpy; +https://github.com/speedyapply/JobSpy)",
}

# Short meaning of each level, as published on https://jobsbylevel.com/levels
level_meanings = {
    1: "AI is not the work",
    2: "AI is a tool",
    3: "AI is daily work",
    4: "AI is the job",
}
