// Example Scripted REST API operation script — update fields on an
// existing incident. Wrap this as a "REST API" category Tool (POST/PUT)
// in the MCP Server Console, with a Request Schema attached (see the
// paired update_incident_schema_example.json).
//
// IMPORTANT: this uses the STANDARD ServiceNow field names (close_code,
// close_notes). On a customized/legacy instance, these may not be the
// fields actually in use — one real build in this pattern found a
// standard-looking field completely unused while a custom `u_`-prefixed
// field held all the real data. Verify field names against real records
// on your target instance before trusting this as-is; don't assume a
// field's existence in the dictionary means it's the one your team
// actually uses.

(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {

    var number = request.pathParams.number;
    if (!number) {
        response.setStatus(400);
        response.setBody({ message: "Incident number is required." });
        return;
    }

    var body = request.body.data || {};

    var gr = new GlideRecordSecure('incident');
    gr.addQuery('number', number);
    gr.query();

    if (!gr.next()) {
        response.setStatus(404);
        response.setBody({ message: "Incident not found: " + number });
        return;
    }

    if (!gr.canWrite()) {
        response.setStatus(403);
        response.setBody({ message: "Not authorized to update incident: " + number });
        return;
    }

    // Simple string fields — set only if provided, so untouched fields
    // stay untouched. Adjust this list to match your instance's real
    // field names (see the note at the top of this file).
    var directFields = ["short_description", "description", "urgency",
                         "impact", "state", "close_code", "close_notes"];
    for (var i = 0; i < directFields.length; i++) {
        var f = directFields[i];
        if (body[f] !== undefined && body[f] !== null) {
            gr.setValue(f, body[f]);
        }
    }

    // Reference fields — resolve by name/username to a single sys_id
    // before setting. setDisplayValue() is intentionally NOT used here:
    // it silently "best matches" on ambiguous/duplicate display names
    // with no error, which is the wrong failure mode for an API a model
    // calls unsupervised.
    if (body.assignment_group !== undefined && body.assignment_group !== null) {
        var groupGr = new GlideRecordSecure('sys_user_group');
        groupGr.addQuery('name', body.assignment_group);
        groupGr.addQuery('active', true);
        groupGr.query();
        var groupMatches = [];
        while (groupGr.next()) {
            groupMatches.push(groupGr.getValue('sys_id'));
        }
        if (groupMatches.length === 0) {
            response.setStatus(400);
            response.setBody({ message: "No active group found matching assignment_group: " + body.assignment_group });
            return;
        }
        if (groupMatches.length > 1) {
            response.setStatus(400);
            response.setBody({ message: "assignment_group '" + body.assignment_group + "' matches more than one active group; use a more specific name." });
            return;
        }
        gr.setValue('assignment_group', groupMatches[0]);
    }

    if (body.assigned_to !== undefined && body.assigned_to !== null) {
        var userGr = new GlideRecordSecure('sys_user');
        userGr.addQuery('user_name', body.assigned_to);
        userGr.addQuery('active', true);
        userGr.query();
        if (!userGr.next()) {
            response.setStatus(400);
            response.setBody({ message: "No active user found with user_name: " + body.assigned_to });
            return;
        }
        gr.setValue('assigned_to', userGr.getValue('sys_id'));
    }

    // Journal fields append via direct property/bracket assignment, NOT
    // setValue() — setValue() on a journal field is documented as
    // unreliable.
    if (body.work_notes) {
        gr.work_notes = body.work_notes;
    }
    if (body.comments) {
        gr.comments = body.comments;
    }

    var updateResult = gr.update();
    if (!updateResult) {
        gs.error("[ServiceNowMCP] Update failed for incident " + number + ": " + gr.getLastErrorMessage());
        response.setStatus(500);
        response.setBody({ message: "Update failed for incident " + number + ": " + gr.getLastErrorMessage() });
        return;
    }

    response.setStatus(200);
    response.setBody({
        sys_id: gr.getValue('sys_id'),
        number: gr.getValue('number'),
        short_description: gr.getValue('short_description'),
        state: gr.getValue('state'),
        urgency: gr.getValue('urgency'),
        impact: gr.getValue('impact'),
        assigned_to: gr.getDisplayValue('assigned_to'),
        assignment_group: gr.getDisplayValue('assignment_group')
    });

})(request, response);
