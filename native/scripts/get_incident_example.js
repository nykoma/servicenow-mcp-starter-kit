// Example Scripted REST API operation script — GET a single incident by number.
// Wrap this as a "REST API" category Tool in the MCP Server Console (no
// schema needed for GET; path parameters auto-expose as Tool Inputs).
//
// This is a starting-point example, not verified against any specific
// instance. Field names, choice values, and ACL behavior can all differ
// on your target instance — check before trusting this as-is.

(function process(/*RESTAPIRequest*/ request, /*RESTAPIResponse*/ response) {
    var number = request.pathParams.number;
    if (!number) {
        response.setStatus(400);
        response.setBody({ message: "Incident number is required." });
        return;
    }

    // GlideRecordSecure, not GlideRecord — enforces the target table's own
    // ACLs, so row-level access still applies underneath whatever the
    // OAuth scope grants. This is not optional for a script an AI client
    // will call unsupervised.
    var gr = new GlideRecordSecure('incident');
    gr.addQuery('number', number);
    gr.query();

    if (!gr.next()) {
        // Note: if the caller lacks read access to this specific record,
        // GlideRecordSecure filters it out of the query results silently
        // — this same 404 fires whether the record doesn't exist or the
        // caller just can't see it. That's correct, secure behavior (it
        // doesn't leak record existence), but worth knowing if you're
        // ever debugging "why does this return 404 when I know the
        // record exists."
        response.setStatus(404);
        response.setBody({ message: "Incident not found: " + number });
        return;
    }

    response.setStatus(200);
    response.setBody({
        sys_id: gr.getValue('sys_id'),
        number: gr.getValue('number'),
        short_description: gr.getValue('short_description'),
        description: gr.getValue('description'),
        state: gr.getValue('state'),
        urgency: gr.getValue('urgency'),
        priority: gr.getValue('priority'),
        assigned_to: gr.getDisplayValue('assigned_to'),
        assignment_group: gr.getDisplayValue('assignment_group'),
        opened_at: gr.getValue('opened_at'),
        caller_id: gr.getDisplayValue('caller_id')
    });
})(request, response);
