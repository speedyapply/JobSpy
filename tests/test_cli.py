
import pytest
import sys
from io import StringIO
from jobspy_cli import parse_args

def run_cli_parser(args_list):
    """Helper to run the CLI parser with a specific list of arguments."""
    sys.argv = ["jobspy_cli.py"] + args_list
    return parse_args()

def test_cli_search_required():
    """Test that the CLI fails gracefully if search term is missing (unless json-input is used)."""
    # This is handled in main(), not parse_args, but we can check if args are parsed correctly
    args = run_cli_parser(["--search", "software engineer"])
    assert args.search == "software engineer"
    assert args.location is None

def test_cli_full_args():
    """Test parsing of all major arguments."""
    args = run_cli_parser([
        "--search", "python",
        "--location", "Remote",
        "--sites", "indeed,linkedin",
        "--results", "20",
        "--hours", "24",
        "--remote",
        "--job-type", "contract",
        "--country", "uk",
        "--format", "json"
    ])
    
    assert args.search == "python"
    assert args.location == "Remote"
    assert args.sites == "indeed,linkedin"
    assert args.results == 20
    assert args.hours == 24
    assert args.remote is True
    assert args.job_type == "contract"
    assert args.country == "uk"
    assert args.format == "json"

def test_cli_defaults():
    """Test default values."""
    args = run_cli_parser(["--search", "test"])
    assert args.results == 15
    assert args.distance == 50
    assert args.country == "usa"
    assert args.format == "json"
    assert args.sites == "indeed,linkedin"
