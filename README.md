# Pexip External Policy Server with Web UI

This project is a powerful, web-based external policy server for Pexip Infinity, built with Flask. It allows administrators to create and manage dynamic, rule-based policies for call control through an intuitive dashboard interface, removing the need to write custom code for each policy change.

## Features

* **Web Dashboard:** A clean, modern dashboard to create, view, edit, and delete policy rules.
* **Dual Policy Support:** Handles both **Service Configuration** and **Participant Properties** policy requests.
* **Dynamic Rule Engine:**
    * Create rules with multiple conditions.
    * Use a variety of operators, including `equals`, `contains`, `does not contain`, and custom `regex`.
    * Set rule **priority** to control the evaluation order.
* **Rule Management:**
    * **Enable/Disable** rules with a simple toggle switch without deleting them.
    * Grouped view to easily distinguish between service and participant rules.
* **Dynamic Overrides:** For `continue` actions, you can dynamically override Pexip's default settings on a per-call basis for both service and participant properties.
* **Database Migrations:** Uses Flask-Migrate (Alembic) to safely manage database schema changes without losing data.
* **CLI Commands:** Includes commands for easy database setup, seeding with default rules, and complete resets for development.

---

## Requirements

* Python 3.8+
* `pip` for package installation

---

## Installation & Setup

Follow these steps to get the application running locally.

### 1. Set Up the Environment

First, clone the repository and create a Python virtual environment.

```bash
# Clone the repository (if you haven't already)
git clone <your-repo-url>
cd <your-repo-folder>

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

### 2. Install Dependencies

Install the required Python packages.

```bash
pip install Flask Flask-SQLAlchemy Flask-Migrate
```

*(**Note:** For easy deployment, you can save your dependencies to a file: `pip freeze > requirements.txt`)*

### 3. Set Up the Database

This application uses Flask-Migrate to manage the database.

```bash
# Set the FLASK_APP environment variable
export FLASK_APP=app.py  # On Windows, use: set FLASK_APP=app.py

# 1. Initialize the migration environment (only run this once per project)
flask db init

# 2. Generate the initial migration script from your models
flask db migrate -m "Initial migration"

# 3. Apply the migration to create the database file
flask db upgrade
```

### 4. (Optional) Seed the Database

You can populate the database with a few default example rules to get started.

```bash
flask seed-db
```

---

## Usage

### 1. Running the Server

Start the Flask development server. The `--host=0.0.0.0` flag is crucial to make the server accessible to other machines on your network, like your Pexip Conferencing Nodes.

```bash
flask run --debug --host=0.0.0.0
```

The server will be running on port `5000`.

### 2. Accessing the Admin Dashboard

Open your web browser and navigate to the admin interface:

`http://<your_server_ip>:5000/admin`

Here, you can manage all your policy rules.

### 3. Configuring Pexip Infinity

In your Pexip Infinity Administrator interface, you need to point your policy profiles to this server's endpoints:

* **Service Configuration URL:** `http://<your_server_ip>:5000/policy/v1/service/configuration`
* **Participant Properties URL:** `http://<your_server_ip>:5000/policy/v1/participant/properties`

---

## Database Management Commands

* **Reset the Database:** To completely wipe and re-seed the database during development, use the custom `reset-db` command.

    ```bash
    flask reset-db
    ```

* **Making Schema Changes:** If you modify the models in `app.py` (e.g., add a new column), follow this two-step process to safely update the database:

    ```bash
    # 1. Generate a new migration script
    flask db migrate -m "A short message about your changes"

    # 2. Apply the changes to the database
    flask db upgrade
    