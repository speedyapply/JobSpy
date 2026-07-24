# JobSpy Project

## Overview
JobSpy is a web application built using FastAPI that allows users to interact with job listings and related functionalities. This README provides an overview of the project structure, setup instructions, and usage guidelines.

## Project Structure
```
JobSpy
├── app
│   ├── main.py          # Main entry point of the application
│   └── __init__.py     # Marks the app directory as a Python package
├── requirements.txt     # Lists the dependencies for the project
├── Dockerfile           # Instructions to build the Docker image
└── README.md            # Documentation for the project
```

## Setup Instructions

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd JobSpy
   ```

2. **Install dependencies:**
   You can install the required dependencies using pip:
   ```
   pip install -r requirements.txt
   ```

3. **Run the application:**
   You can run the application locally using Uvicorn:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Docker Setup
To build and run the application using Docker, follow these steps:

1. **Build the Docker image:**
   ```
   docker build -t jobspy .
   ```

2. **Run the Docker container:**
   ```
   docker run -d -p 8000:8000 jobspy
   ```

## Usage
Once the application is running, you can access it at `http://localhost:8000`. The API documentation is available at `http://localhost:8000/docs`.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.