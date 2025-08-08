document.addEventListener('DOMContentLoaded', () => {
    // --- Field lists ---
    const PARTICIPANT_FIELDS = ["call_direction", "protocol", "bandwidth", "vendor", "encryption", "registered", "trigger", "remote_display_name", "remote_alias", "remote_address", "remote_port", "call_tag", "idp_uuid", "has_authenticated_display_name", "supports_direct_media", "teams_tenant_id", "third_party_passcode", "display_count", "location", "node_ip", "version_id", "pseudo_version_id", "preauthenticated_role", "bypass_lock", "receive_from_audio_mix", "layout_group", "spotlight", "disable_overlay_text", "prefers_multiscreen_mix", "wants_presentation_in_mix", "can_receive_personal_mix", "rx_presentation_policy", "participant_type", "participant_uuid", "local_alias", "call_uuid", "breakout_uuid", "idp_attribute_rank", "idp_attribute_service", "idp_attribute_clearance", "idp_attribute_country", "send_to_audio_mixes_mix_name", "send_to_audio_mixes_prominent", "receive_from_video_mix~mix_name", "unique_service_name", "service_name", "service_tag", "request_id"];
    const PARTICIPANT_OVERRIDE_FIELDS = ["bypass_lock", "call_tag", "can_receive_personal_mix", "display_count", "disable_overlay_text", "layout_group", "preauthenticated_role", "prefers_multiscreen_mix", "remote_alias", "remote_display_name", "rx_presentation_policy", "spotlight", "wants_presentation_in_mix"];

    // --- DOM Elements ---
    const rulesContainer = document.getElementById('rules-container');
    const ruleForm = document.getElementById('rule-form');
    const policyTestForm = document.getElementById('policy-test-form');
    const testResponseOutput = document.getElementById('test-response-output');
    const testParamsContainer = document.getElementById('test-params-container');
    const addTestParamBtn = document.getElementById('add-test-param-btn');
    const formTitle = document.getElementById('form-title');
    const conditionsContainer = document.getElementById('conditions-container');
    const addConditionBtn = document.getElementById('add-condition-btn');
    const actionTypeSelect = document.getElementById('action-type');
    const actionParamsContainer = document.getElementById('action-params-container');
    const editingRuleIdInput = document.getElementById('editing-rule-id');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const showCreateFormBtn = document.getElementById('show-create-form-btn');

    policyTestForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const params = new URLSearchParams();

        // Gather all the dynamic key-value pairs
        document.querySelectorAll('.test-param-row').forEach(row => {
            const key = row.querySelector('.test-param-key').value;
            const value = row.querySelector('.test-param-value').value;
            if (key && value) {
                params.append(key, value);
            }
        });

        const response = await fetch(`/admin/api/test-policy?${params.toString()}`);
        const data = await response.json();

        testResponseOutput.textContent = JSON.stringify(data, null, 2);
    });

    // --- Core Functions ---
    const fetchRules = async () => {
        const response = await fetch('/admin/api/rules');
        const rules = await response.json();
        const participantRules = rules.filter(r => r.policy_type === 'participant');
        renderRules(participantRules);
        updateStats(participantRules);
    };

    const updateStats = (rules) => {
        document.getElementById('total-rules-stat').textContent = rules.length;
    };

    const renderRules = (rules) => {
        rulesContainer.innerHTML = '';
        if (rules.length === 0) {
            rulesContainer.innerHTML = '<p>No rules defined yet.</p>';
            return;
        }
        rules.forEach(rule => renderRuleCard(rule));
    };
    
    const renderRuleCard = (rule) => {
        const ruleEl = document.createElement('div');
        ruleEl.className = `rule-card-slim ${!rule.is_enabled ? 'rule-disabled' : ''}`;
        ruleEl.dataset.ruleId = rule.id;
        let actionText = rule.action.type;
        if (rule.action.type === 'redirect' && rule.action.parameters && rule.action.parameters.destination) {
            actionText += ` → ${rule.action.parameters.destination}`;
        } else if (rule.action.type === 'reject' && rule.action.reject_reason) {
            actionText += ` (${rule.action.reject_reason})`;
        } else if (rule.action.type === 'continue' && Object.keys(rule.action.overrides).length > 0) {
            actionText += ` (with overrides)`;
        }
        ruleEl.innerHTML = `
            <div class="rule-status"><label class="toggle-switch"><input type="checkbox" class="status-toggle" data-id="${rule.id}" ${rule.is_enabled ? 'checked' : ''}><span class="slider"></span></label></div>
            <div class="rule-info"><span class="rule-priority">(P${rule.priority})</span><span class="rule-name">${rule.name}</span></div>
            <div class="rule-details"><span class="rule-conditions">IF: ${rule.conditions.map(c => `${c.field} ${c.operator} "${c.value}"`).join(', ')}</span><span class="rule-action">THEN: ${actionText}</span></div>
            <div class="rule-buttons"><button class="edit-btn" data-id="${rule.id}">Edit</button><button class="delete-btn" data-id="${rule.id}">Delete</button></div>
        `;
        rulesContainer.appendChild(ruleEl);
    };
    
    const addConditionRow = (condition = {}) => {
        const row = document.createElement('div');
        row.className = 'condition-row';
        row.innerHTML = `<select class="condition-field" required></select><select class="condition-operator"><option value="equals">equals</option><option value="contains">contains</option><option value="does_not_contain">does not contain</option><option value="starts_with">starts with</option><option value="ends_with">ends with</option><option value="regex">regex</option></select><input type="text" class="condition-value" placeholder="Value / Regex Pattern" required><button type="button" class="remove-condition-btn">-</button>`;
        row.querySelector('.condition-operator').value = condition.operator || 'equals';
        row.querySelector('.condition-value').value = condition.value || '';
        conditionsContainer.appendChild(row);
        updateConditionFieldDropdown(row.querySelector('.condition-field'), condition.field);
        row.querySelector('.remove-condition-btn').addEventListener('click', () => row.remove());
    };

    const addOverrideRow = (key = "", value = "") => {
        const container = document.getElementById('overrides-container');
        const row = document.createElement('div');
        row.className = 'override-row';
        const keySelect = document.createElement('select');
        keySelect.className = 'override-key';
        keySelect.innerHTML = `<option value="" disabled>Select setting...</option>`;
        PARTICIPANT_OVERRIDE_FIELDS.forEach(field => keySelect.add(new Option(field, field)));
        keySelect.value = key;
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'override-value';
        valueInput.placeholder = 'Value (e.g., true, chair)';
        valueInput.value = value;
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-condition-btn';
        removeBtn.textContent = '-';
        removeBtn.onclick = () => row.remove();
        row.append(keySelect, valueInput, removeBtn);
        container.appendChild(row);
    };

    const resetForm = () => {
        ruleForm.reset();
        editingRuleIdInput.value = '';
        conditionsContainer.innerHTML = '';
        actionParamsContainer.innerHTML = '';
        formTitle.textContent = 'Create New Rule';
        document.getElementById('save-update-btn').textContent = 'Save Rule';
        cancelEditBtn.style.display = 'none';
        addConditionRow();
        updateActionParams();
    };

    const populateFormForEdit = (rule) => {
        resetForm();
        formTitle.textContent = `Editing Rule`;
        document.getElementById('save-update-btn').textContent = 'Update Rule';
        cancelEditBtn.style.display = 'block';
        editingRuleIdInput.value = rule.id;
        document.getElementById('rule-name').value = rule.name;
        document.getElementById('rule-priority').value = rule.priority;
        conditionsContainer.innerHTML = '';
        rule.conditions.forEach(addConditionRow);
        actionTypeSelect.value = rule.action.type;
        updateActionParams();
        if (rule.action.type === 'redirect' && rule.action.parameters) {
            document.getElementById('action-param-destination').value = rule.action.parameters.destination;
        }
        if (rule.action.type === 'reject' && rule.action.reject_reason) {
            document.getElementById('action-param-reject-reason').value = rule.action.reject_reason;
        }
        if (rule.action.type === 'continue' && rule.action.overrides) {
            Object.entries(rule.action.overrides).forEach(([key, value]) => {
                addOverrideRow(key, value);
            });
        }
    };
    
    const updateConditionFieldDropdown = (selectElement, selectedValue = "") => {
        selectElement.innerHTML = '<option value="" disabled>Select field...</option>';
        PARTICIPANT_FIELDS.forEach(field => selectElement.add(new Option(field, field)));
        selectElement.value = selectedValue;
    };

    const updateActionParams = () => {
        actionParamsContainer.innerHTML = '';
        const action = actionTypeSelect.value;
        if (action === 'redirect') {
            actionParamsContainer.innerHTML = `<input type="text" id="action-param-destination" placeholder="Redirect Destination (e.g. sip:..)" required>`;
        } else if (action === 'reject') {
            actionParamsContainer.innerHTML = `<input type="text" id="action-param-reject-reason" placeholder="Optional Reject Reason">`;
        } else if (action === 'continue') {
            actionParamsContainer.innerHTML = `<div class="overrides-container" id="overrides-container"></div><button type="button" id="add-override-btn">＋ Add Override</button>`;
            document.getElementById('add-override-btn').onclick = () => addOverrideRow();
        }
    };
    
    const addTestParamRow = (key = "", value = "") => {
        const row = document.createElement('div');
        row.className = 'test-param-row';

        const keySelect = document.createElement('select');
        keySelect.className = 'test-param-key';
        keySelect.innerHTML = `<option value="" disabled>Select parameter...</option>`;
        // For simplicity, we'll allow any participant field in the tester
        PARTICIPANT_FIELDS.forEach(field => keySelect.add(new Option(field, field)));
        keySelect.value = key;

        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'test-param-value';
        valueInput.placeholder = 'Value';
        valueInput.value = value;

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-condition-btn';
        removeBtn.textContent = '-';
        removeBtn.onclick = () => row.remove();

        row.append(keySelect, valueInput, removeBtn);
        testParamsContainer.appendChild(row);
    };

    // --- Event Listeners ---
    addConditionBtn.addEventListener('click', addConditionRow);
    actionTypeSelect.addEventListener('change', updateActionParams);
    cancelEditBtn.addEventListener('click', resetForm);
    showCreateFormBtn.addEventListener('click', resetForm);

    ruleForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const ruleId = editingRuleIdInput.value;
        const ruleData = {
            name: document.getElementById('rule-name').value,
            priority: parseInt(document.getElementById('rule-priority').value),
            policy_type: 'participant', // Hardcode to 'participant'
            conditions: Array.from(document.querySelectorAll('.condition-row')).map(row => ({
                field: row.querySelector('.condition-field').value,
                operator: row.querySelector('.condition-operator').value,
                value: row.querySelector('.condition-value').value,
            })),
            action: { type: actionTypeSelect.value, parameters: {}, reject_reason: null, overrides: {} }
        };

        if (ruleData.action.type === 'redirect') {
            ruleData.action.parameters = { destination: document.getElementById('action-param-destination').value };
        } else if (ruleData.action.type === 'reject') {
            ruleData.action.reject_reason = document.getElementById('action-param-reject-reason').value;
        } else if (ruleData.action.type === 'continue') {
            document.querySelectorAll('.override-row').forEach(row => {
                const key = row.querySelector('.override-key').value;
                const value = row.querySelector('.override-value').value;
                if (key && value !== '') {
                    let finalValue = value;
                    if (value.toLowerCase() === 'true') finalValue = true;
                    else if (value.toLowerCase() === 'false') finalValue = false;
                    else if (!isNaN(value) && value.trim() !== '') finalValue = Number(value);
                    ruleData.action.overrides[key] = finalValue;
                }
            });
        }
        
        const url = ruleId ? `/admin/api/rules/${ruleId}` : '/admin/api/rules';
        const method = ruleId ? 'PUT' : 'POST';
        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(ruleData),
        });

        if (response.ok) {
            resetForm();
        } else {
            alert(`Failed to ${method === 'POST' ? 'save' : 'update'} rule.`);
        }
        await fetchRules();
    });

    rulesContainer.addEventListener('click', async (e) => {
        const target = e.target;
        const ruleId = target.dataset.id;
        if (target.classList.contains('delete-btn')) {
            if (confirm('Are you sure you want to delete this rule?')) {
                const response = await fetch(`/admin/api/rules/${ruleId}`, { method: 'DELETE' });
                if (response.ok) {
                    resetForm();
                    await fetchRules();
                } else {
                    alert('Failed to delete rule.');
                }
            }
        } else if (target.classList.contains('edit-btn')) {
            const response = await fetch(`/admin/api/rules/${ruleId}`);
            if (response.ok) {
                const rule = await response.json();
                populateFormForEdit(rule);
            } else {
                alert('Failed to fetch rule details.');
            }
        } else if (target.classList.contains('status-toggle')) {
            const response = await fetch(`/admin/api/rules/${ruleId}/toggle`, { method: 'POST' });
            if (response.ok) {
                const data = await response.json();
                const ruleCard = document.querySelector(`.rule-card-slim[data-rule-id="${ruleId}"]`);
                if (ruleCard) {
                    ruleCard.classList.toggle('rule-disabled', !data.is_enabled);
                }
            } else {
                alert('Failed to update rule status.');
                target.checked = !target.checked;
            }
        }
    });

    addTestParamBtn.addEventListener('click', () => addTestParamRow());

    // --- Initial Load ---
    fetchRules();
    resetForm();
    addTestParamRow("remote_alias", "user@example.com");
    addTestParamRow("local_alias", "conference.alias");
});