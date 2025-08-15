# Use the official Python 3.13 slim image as the base
FROM python:3.13-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's source code into the container
COPY . .

# Command to run your application when the container starts
CMD ["python", "main.py"]