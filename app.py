import json
import re
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# --- App & DB Setup ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rules_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)


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
    parameters = db.Column(db.Text)      # For redirect destination
    reject_reason = db.Column(db.String(255))
    overrides = db.Column(db.Text)        # For service/participant overrides


# --- Helper Functions ---
def evaluate_condition(request_value, operator, rule_value):
    if operator == 'equals': return request_value == rule_value
    if operator == 'contains': return rule_value in request_value
    if operator == 'does_not_contain': return rule_value not in request_value
    if operator == 'starts_with': return request_value.startswith(rule_value)
    if operator == 'ends_with': return request_value.endswith(rule_value)
    if operator == 'regex':
        try:
            return re.search(rule_value, request_value) is not None
        except re.error as e:
            print(f"Invalid regex pattern '{rule_value}': {e}")
            return False
    return False

# --- This helper function is re-introduced to keep the code clean ---
def build_policy_response(rule):
    """Helper to build the custom JSON response with a nested result."""
    action_type = rule.action.action_type
    # Add the 'status' key to all responses
    response_data = {'status': 'success', 'action': action_type}

    if action_type == 'reject':
        reason = rule.action.reject_reason or 'Rejected by policy'
        response_data['result'] = {'reject_reason': reason}
    elif action_type == 'redirect':
        params = json.loads(rule.action.parameters) if rule.action.parameters else {}
        response_data['result'] = params # e.g., {'destination': '...'}
    elif action_type == 'continue':
        if rule.action.overrides:
            overrides = json.loads(rule.action.overrides)
            response_data['result'] = overrides
            
    print(f"Matched Rule: {rule.name}. Responding with: {json.dumps(response_data)}")
    return jsonify(response_data)

# --- Policy Endpoints ---
@app.route('/policy/v1/service/configuration', methods=['GET'])
def service_configuration():
    request_data = dict(request.args)
    rules = Rule.query.filter_by(policy_type='service', is_enabled=True).order_by(Rule.priority.desc(), Rule.id.asc()).all()
    for rule in rules:
        if all(evaluate_condition(request_data.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
            return build_policy_response(rule)
    return jsonify({"status": "success", "action": "continue"})

@app.route('/policy/v1/participant/properties', methods=['GET'])
def participant_properties():
    request_data = dict(request.args)
    rules = Rule.query.filter_by(policy_type='participant', is_enabled=True).order_by(Rule.priority.desc(), Rule.id.asc()).all()
    for rule in rules:
        if all(evaluate_condition(request_data.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
            return build_policy_response(rule)
    return jsonify({"status": "success", "action": "continue"})

# --- Admin UI & API (Full, Correct Versions) ---
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/admin/api/rules', methods=['GET', 'POST'])
def handle_rules_collection():
    if request.method == 'POST':
        data = request.json
        new_rule = Rule(name=data['name'], priority=data['priority'], policy_type=data['policy_type'])
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
        return jsonify({'status': 'success', 'id': new_rule.id})

    rules_query = Rule.query.order_by(Rule.priority.desc()).all()
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
        rule.priority = data['priority']
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
    """
    A safe endpoint for the UI to test participant policy rules.
    This uses the exact same logic as the real endpoint.
    """
    request_data = dict(request.args)
    # The logic here is identical to the production participant_properties endpoint
    rules = Rule.query.filter_by(policy_type='participant', is_enabled=True).order_by(Rule.priority.desc(), Rule.id.asc()).all()
    for rule in rules:
        if all(evaluate_condition(request_data.get(c.field, ''), c.operator, c.value) for c in rule.conditions):
            return build_policy_response(rule)
    return jsonify({"action": "continue"})

# --- Database Seeding Commands ---
def _seed_database():
    if Rule.query.first():
        print("Database already seeded. Skipping.")
        return
    print("Seeding database with default rules...")
    rule1 = Rule(name="Block CAPT rank", priority=200, policy_type="participant")
    rule1.action = Action(action_type="reject", reject_reason="This rank is not permitted.")
    rule1.conditions.append(Condition(field="idp_attribute_rank", operator="equals", value="CAPT"))
    rule2 = Rule(name="Redirect sales alias", priority=150, policy_type="service")
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
    db.drop_all()
    print("Database tables dropped.")
    db.create_all()
    print("Database tables created.")
    _seed_database()