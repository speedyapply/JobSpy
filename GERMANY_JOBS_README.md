# JobSpy - Germany IT Jobs Search Script

This repository includes a ready-to-use Python script for searching IT and Software Engineering jobs in Germany.

## Quick Start

```bash
# Install dependencies
pip install python-jobspy

# Run the job search script
python search_germany_jobs.py
```

The script will:
- Search for IT/Software jobs in Berlin and Germany
- Filter jobs posted in the last 7 days
- Save results to a timestamped CSV file
- Display a summary of found jobs

## What's Included

- **`search_germany_jobs.py`**: Main script for searching IT jobs in Germany
- **`USAGE_GUIDE.md`**: Comprehensive documentation and customization guide

## Job Search Details

### Covered Positions
- Software Engineer / Developer
- DevOps Engineer
- Site Reliability Engineer (SRE)
- System Engineer
- Backend / Full Stack Developer
- Python / Java Developer

### Search Locations
1. **Berlin** (Priority)
2. **Germany** (General)

### Job Boards
- Indeed
- LinkedIn
- Google Jobs

### Time Filter
- Last 7 days (168 hours)

## Example Output

The script generates a CSV file like `germany_it_jobs_20260204_190052.csv` containing:
- Job title
- Company name
- Location
- Job type
- Job board source
- Date posted
- Job URL
- Full description
- Salary information (when available)

## Customization

The script can be easily customized by editing `search_germany_jobs.py`:

- **Add/remove search terms**: Modify the `search_terms` list
- **Change time filter**: Adjust `hours_old` variable (e.g., `24 * 3` for 3 days)
- **Add more locations**: Add additional search blocks for other cities
- **Change job boards**: Modify the `sites` list
- **Adjust results count**: Change `results_wanted` parameter

See `USAGE_GUIDE.md` for detailed customization instructions.

## Requirements

- Python 3.10+
- python-jobspy package
- Internet connection

## Documentation

For detailed usage instructions, troubleshooting, and customization options, see:
- **[USAGE_GUIDE.md](USAGE_GUIDE.md)** - Complete usage guide
- **[README.md](README.md)** - JobSpy library documentation

## Notes

- The script respects rate limits - if you encounter errors, try reducing search scope
- Results are automatically deduplicated
- Berlin jobs appear first in the sorted output

## Support

For JobSpy library issues or questions, visit:
https://github.com/cullenwatson/JobSpy
