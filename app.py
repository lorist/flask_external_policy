import json
import re
import logging
from logging.handlers import RotatingFileHandler
import time
from flask import Flask, request, jsonify, render_template, Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# --- App & DB Setup ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rules_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Logging Configuration ---
log_file = 'policy_server.log'
file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 5, backupCount=5)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s'
))
app.logger.setLevel(logging.DEBUG) # Keep in debug mode for now
app.logger.addHandler(file_handler)
app.logger.info('--- Policy Server Startup ---')


# --- SQLAlchemy Models ---
class Rule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    policy_type = db.Column(db.String(50), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    conditions = db.relationship('Condition', backref='rule', lazy=True, cascade="all, delete-orphan")
    action = db.relationship('Action', uselist=False, backref='rule', lazy=True, cascade="all, delete-orphan")

class Condition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('rule.id'), nullable=False)
    field = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(255), nullable=False)

class Action(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('rule.id'), nullable=False)
    action_type = db.Column('action', db.String(50), nullable=False)
    parameters = db.Column(db.Text)
    reject_reason = db.Column(db.String(255))
    overrides = db.Column(db.Text)


# --- Helper Functions ---
def evaluate_condition(request_value, operator, rule_value):
    request_value_str = str(request_value) if request_value is not None else ''
    app.logger.debug(f"EVALUATING: |{request_value_str}| {operator} |{rule_value}|")

    match_result = False
    if operator == 'equals':
        match_result = (request_value_str == rule_value)
    elif operator == 'contains':
        match_result = (rule_value in request_value_str)
    elif operator == 'does_not_contain':
        match_result = (rule_value not in request_value_str)
    elif operator == 'starts_with':
        match_result = request_value_str.startswith(rule_value)
    elif operator == 'ends_with':
        match_result = request_value_str.endswith(rule_value)
    elif operator == 'regex_match': # Check for the correct operator key
        try:
            match_result = (re.search(rule_value, request_value_str) is not None)
        except re.error as e:
            app.logger.error(f"Invalid regex pattern '{rule_value}': {e}")
            match_result = False

    app.logger.debug(f"--> RESULT: {'MATCH' if match_result else 'NO MATCH'}")
    return match_result

def build_policy_response(rule):
    action_type = rule.action.action_type
    response_data = {'status': 'success', 'action': action_type}
    if action_type == 'reject':
        reason = rule.action.reject_reason or 'Rejected by policy'
        response_data['result'] = {'reject_reason': reason}
    elif action_type == 'redirect':
        params = json.loads(rule.action.parameters) if rule.action.parameters else {}
        response_data['result'] = params
    elif action_type == 'continue':
        if rule.action.overrides:
            overrides = json.loads(rule.action.overrides)
            response_data['result'] = overrides
    return jsonify(response_data)

def map_operator_to_jinja(op):
    """
    Translates our app's operator to a Jinja2/Python equivalent.
    """
    return {
        'equals': '==',
        'contains': 'in',
        'does_not_contain': 'not in',
        'starts_with': '.startswith',
        'ends_with': '.endswith',
        'regex_match': 'pex_regex_match' # Use the correct operator key
    }.get(op, '==')

@app.route('/admin/api/export-policy', methods=['GET'])
def export_participant_policy():
    """
    Exports rules to the Pexip Local Policy format, using the
    {% set %} variable method for regex conditions.
    """
    rules = Rule.query.filter_by(policy_type='participant', is_enabled=True).order_by(Rule.priority.asc()).all()

    if not rules:
        return jsonify({"policy": "{\n  \"status\": \"success\",\n  \"action\": \"continue\",\n  \"result\": {{ participant|pex_to_json }}\n}"})

    policy_lines = ['{', '  "status": "success",', '  "action": "continue",']
    
    # Pass 1: Find all regex conditions and create {% set %} statements
    set_statements = []
    regex_variable_map = {} # Maps a condition ID to its variable name
    for rule in rules:
        for c in rule.conditions:
            if c.operator == 'regex_match':
                # Create a unique, descriptive variable name
                var_name = f"match_rule{rule.id}_field_{c.field.replace('_','')}"
                # The regex pattern must be in a capture group (...) for pex_regex_search
                pattern = f"({c.value})"
                # Store the variable name for use in Pass 2
                regex_variable_map[c.id] = var_name
                # Create the Jinja2 'set' statement
                set_line = f'  {{% set {var_name} = pex_regex_search("{pattern}", call_info.get("{c.field}", "")) %}}'
                if set_line not in set_statements:
                     set_statements.append(set_line)

    policy_lines.extend(set_statements)
    
    # Pass 2: Build the 'result' block with if/elif/else
    result_lines = []
    for i, rule in enumerate(rules):
        conditions = []
        for c in rule.conditions:
            if c.operator == 'regex_match':
                # For regex, we just check if the variable we set earlier exists
                conditions.append(regex_variable_map.get(c.id))
            else:
                # For other operators, build the condition as before
                jinja_op = map_operator_to_jinja(c.operator)
                if c.operator in ['starts_with', 'ends_with']:
                    conditions.append(f"call_info.get('{c.field}', '') {jinja_op}('{c.value}')")
                else:
                    conditions.append(f"call_info.get('{c.field}') {jinja_op} '{c.value}'")

        # Filter out any None values in case a regex variable wasn't found (should not happen)
        valid_conditions = [cond for cond in conditions if cond]
        condition_expression = " and ".join(valid_conditions)

        if i == 0:
            result_lines.append(f'  "result": {{% if {condition_expression} %}}')
        else:
            result_lines.append(f'            {{% elif {condition_expression} %}}')

        # Action-building logic (unchanged)
        action_type = rule.action.action_type
        if action_type == 'continue' and rule.action.overrides:
            overrides = json.loads(rule.action.overrides)
            overrides_str = json.dumps(overrides, indent=14).strip('{}').strip()
            result_lines.append(f'              {{{{ participant|pex_update({{\n                {overrides_str}\n              }})|pex_to_json }}}}')
        elif action_type == 'reject':
            reason = rule.action.reject_reason or "Call rejected by policy"
            result_lines.append(f'              {{"action": "reject", "reason": "{reason}"}}')
        elif action_type == 'redirect':
            params = json.loads(rule.action.parameters) if rule.action.parameters else {}
            destination = params.get('destination', '')
            result_lines.append(f'              {{"action": "redirect", "destination": "{destination}"}}')
        else:
             result_lines.append('              {{ participant|pex_to_json }}')

    result_lines.append('            {% else %}')
    result_lines.append('              {{ participant|pex_to_json }}')
    result_lines.append('            {% endif %}')
    
    policy_lines.extend(result_lines)
    policy_lines.append('}')

    return jsonify({"policy": "\n".join(policy_lines)})

# --- Policy Endpoints (Updated with Logging) ---
@app.route('/policy/v1/service/configuration', methods=['GET'])
def service_configuration():
    app.logger.info(f"--> SERVICE REQUEST: {request.url}")
    # rules = Rule.query.filter_by(policy_type='service', is_enabled=True).order_by(Rule.priority.asc()).all()
    # for rule in rules:
    #     if all(evaluate_condition(request.args.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
    #         response = build_policy_response(rule)
    #         app.logger.info(f"<-- RESPONSE: Matched '{rule.name}'. Sending {response.get_data(as_text=True).strip()}")
    #         return response
    app.logger.info("<-- RESPONSE: No match. Sending default 'continue'.")
    return jsonify({"status": "success", "action": "continue"})

@app.route('/policy/v1/participant/properties', methods=['GET'])
def participant_properties():
    app.logger.info(f"--> PARTICIPANT REQUEST: {request.url}")
    rules = Rule.query.filter_by(policy_type='participant', is_enabled=True).order_by(Rule.priority.asc()).all()
    for rule in rules:
        if all(evaluate_condition(request.args.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
            response = build_policy_response(rule)
            app.logger.info(f"<-- RESPONSE: Matched '{rule.name}'. Sending {response.get_data(as_text=True).strip()}")
            return response
    app.logger.info("<-- RESPONSE: No match. Sending default 'continue'.")
    return jsonify({"status": "success", "action": "continue"})


# --- Admin UI & API ---
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# --- Log Viewer Endpoints ---
@app.route('/admin/logs')
def log_viewer_page():
    """Renders the log viewer page."""
    return render_template('log_viewer.html')

@app.route('/admin/log-stream')
def log_stream():
    """Streams the contents of the log file to the client."""
    def generate():
        try:
            with open(log_file, 'r') as f:
                f.seek(0, 2) # Go to the end of the file
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    yield f"data: {line}\n\n"
        except FileNotFoundError:
            app.logger.warning(f"Log file '{log_file}' not found. Creating it.")
            # Create the file if it doesn't exist so the stream doesn't break
            with open(log_file, 'w') as f:
                f.write("Log file created.\n")
            yield "data: Log file created.\n\n"

    return Response(generate(), mimetype='text/event-stream')

# --- Admin API for Rules ---
@app.route('/admin/api/rules', methods=['GET', 'POST'])
def handle_rules_collection():
    if request.method == 'POST':
        data = request.json
        last_priority = db.session.query(db.func.max(Rule.priority)).scalar()
        new_priority = (last_priority or -1) + 1

        new_rule = Rule(name=data['name'], priority=new_priority, policy_type=data['policy_type'])
        
        new_action = Action(
            action_type=data['action']['type'],
            parameters=json.dumps(data['action']['parameters']),
            reject_reason=data['action'].get('reject_reason'),
            overrides=json.dumps(data['action'].get('overrides'))
        )
        new_rule.action = new_action
        for c_data in data['conditions']:
            new_rule.conditions.append(Condition(**c_data))
        db.session.add(new_rule)
        db.session.commit()
        return jsonify({'status': 'success', 'id': new_rule.id}), 201

    rules_query = Rule.query.order_by(Rule.priority.asc()).all()
    rules_list = []
    for rule in rules_query:
        rule_dict = {
            'id': rule.id, 'name': rule.name, 'priority': rule.priority, 
            'policy_type': rule.policy_type, 'is_enabled': rule.is_enabled,
            'conditions': [{'field': c.field, 'operator': c.operator, 'value': c.value} for c in rule.conditions],
            'action': {
                'type': rule.action.action_type,
                'parameters': json.loads(rule.action.parameters) if rule.action.parameters else {},
                'reject_reason': rule.action.reject_reason,
                'overrides': json.loads(rule.action.overrides) if rule.action.overrides else {}
            }
        }
        rules_list.append(rule_dict)
    return jsonify(rules_list)

@app.route('/admin/api/rules/reorder', methods=['POST'])
def reorder_rules():
    data = request.json
    rule_ids_in_order = data.get('order', [])
    
    try:
        for index, rule_id in enumerate(rule_ids_in_order):
            rule = Rule.query.get(rule_id)
            if rule:
                rule.priority = index
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error reordering rules: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/admin/api/rules/<int:rule_id>/toggle', methods=['POST'])
def toggle_rule_status(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    rule.is_enabled = not rule.is_enabled
    db.session.commit()
    return jsonify({'status': 'success', 'is_enabled': rule.is_enabled})

@app.route('/admin/api/rules/<int:rule_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    if request.method == 'GET':
        rule_dict = {
            'id': rule.id, 'name': rule.name, 'priority': rule.priority, 
            'policy_type': rule.policy_type, 'is_enabled': rule.is_enabled,
            'conditions': [{'field': c.field, 'operator': c.operator, 'value': c.value} for c in rule.conditions],
            'action': {
                'type': rule.action.action_type,
                'parameters': json.loads(rule.action.parameters) if rule.action.parameters else {},
                'reject_reason': rule.action.reject_reason,
                'overrides': json.loads(rule.action.overrides) if rule.action.overrides else {}
            }
        }
        return jsonify(rule_dict)
    elif request.method == 'PUT':
        data = request.json
        rule.name = data['name']
        rule.policy_type = data['policy_type']
        rule.action.action_type = data['action']['type']
        rule.action.parameters = json.dumps(data['action']['parameters'])
        rule.action.reject_reason = data['action'].get('reject_reason')
        rule.action.overrides = json.dumps(data['action'].get('overrides'))
        rule.conditions.clear()
        for c_data in data['conditions']:
            rule.conditions.append(Condition(**c_data))
        db.session.commit()
        return jsonify({'status': 'success', 'id': rule.id})
    elif request.method == 'DELETE':
        db.session.delete(rule)
        db.session.commit()
        return jsonify({'status': 'success'})

@app.route('/admin/api/test-policy', methods=['GET'])
def test_participant_policy():
    log_enabled = request.args.get('log_enabled') == 'true'
    
    if log_enabled:
        app.logger.info(f"--> [TEST] PARTICIPANT REQUEST: {request.url.split('&log_enabled=true')[0]}")

    request_data = dict(request.args)
    rules = Rule.query.filter_by(policy_type='participant', is_enabled=True).order_by(Rule.priority.asc()).all()
    
    for rule in rules:
        if all(evaluate_condition(request_data.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
            response = build_policy_response(rule)
            if log_enabled:
                app.logger.info(f"<-- [TEST] RESPONSE: Matched '{rule.name}'. Sending {response.get_data(as_text=True).strip()}")
            return response
            
    if log_enabled:
        app.logger.info("<-- [TEST] RESPONSE: No match. Sending default 'continue'.")
        
    return jsonify({"action": "continue"})


# --- Database Seeding Commands (for development) ---
def _seed_database():
    if Rule.query.first():
        print("Database already seeded. Skipping.")
        return
    print("Seeding database with default rules...")
    rule1 = Rule(name="Block CAPT rank", priority=0, policy_type="participant", is_enabled=True)
    rule1.action = Action(action_type="reject", reject_reason="This rank is not permitted.")
    rule1.conditions.append(Condition(field="idp_attribute_rank", operator="equals", value="CAPT"))
    
    rule2 = Rule(name="Redirect sales alias", priority=1, policy_type="service", is_enabled=False)
    rule2.action = Action(action_type="redirect", parameters=json.dumps({"destination": "sales.vmr@example.com"}))
    rule2.conditions.append(Condition(field="local_alias", operator="equals", value="sales"))
    
    db.session.add(rule1)
    db.session.add(rule2)
    db.session.commit()
    print("Database seeding complete.")

@app.cli.command("seed-db")
def seed_db_command():
    _seed_database()

@app.cli.command("reset-db")
def reset_db_command():
    print("Dropping all database tables...")
    db.drop_all()
    print("Creating all database tables...")
    db.create_all()
    print("Seeding database with initial data...")
    _seed_database()

if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(host='0.0.0.0', port=5001, debug=True)