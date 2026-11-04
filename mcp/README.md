# mcp-jobspy

<p align="center">
  <a href="https://pypi.org/project/mcp-jobspy/"><img src="https://img.shields.io/pypi/v/mcp-jobspy" alt="PyPI version"></a>
  <a href="https://github.com/speedyapply/JobSpy/actions/workflows/ci.yml"><img src="https://github.com/speedyapply/JobSpy/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/speedyapply/JobSpy/blob/main/mcp/LICENSE"><img src="https://img.shields.io/pypi/l/mcp-jobspy" alt="License: MIT"></a>
  <a href="https://discord.gg/v7WdHnrNcN"><img src="https://img.shields.io/discord/1227411661221269565?label=discord&logo=discord&logoColor=white" alt="Discord"></a>
</p>

[JobSpy](https://github.com/speedyapply/JobSpy)'s MCP server lets AI agents search LinkedIn, Indeed, Glassdoor, ZipRecruiter, Bayt, Naukri, BDJobs, HelloWork and TechJobs.vn. It installs [`python-jobspy[mcp]`](https://pypi.org/project/python-jobspy/) at the same version and runs its `mcp-jobspy` command.

## Setup

Most clients take this config:

```json
{
  "mcpServers": {
    "jobspy": {
      "command": "uvx",
      "args": ["mcp-jobspy@latest"]
    }
  }
}
```

For Claude Code:

```
claude mcp add jobspy -- uvx mcp-jobspy@latest
```

## Tools

- `search_jobs` searches the boards and returns a preview of each job with a search id. It takes JobSpy's search options (keywords, location, boards, number per board, posting age, remote, job type and more) and can save every record to a `.csv`, `.json` or `.jsonl` file.
- `get_job_details` returns the full records of chosen jobs from a search, without searching again.

## Proxies

Job boards block repeated searches. Give the agent a proxy or a list of them, or set `HTTPS_PROXY` in the server's environment to keep credentials out of the chat:

```json
{
  "mcpServers": {
    "jobspy": {
      "command": "uvx",
      "args": ["mcp-jobspy@latest"],
      "env": {"HTTPS_PROXY": "http://user:pass@host:port"}
    }
  }
}
```

<!-- mcp-name: io.github.speedyapply/jobspy -->
