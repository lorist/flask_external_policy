# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Create a non-root user and switch to it for better security
RUN useradd --create-home appuser
USER appuser

# Expose the port the app will run on
EXPOSE 5001

# Define the command to run the application using Gunicorn
# This will be the entrypoint for the container
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app"]