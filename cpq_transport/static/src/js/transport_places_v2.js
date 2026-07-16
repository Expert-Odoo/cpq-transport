/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { useInputField } from "@web/views/fields/input_field_hook";
import { rpc } from "@web/core/network/rpc";

export class TransportPlacesAutocompleteV2 extends CharField {
    static template = "cpq_transport.TransportPlacesAutocompleteV2";
    static components = { AutoComplete, ...CharField.components };

    setup() {
        super.setup();
        this.input = useChildRef();
        this.orm = useService("orm");
        useInputField({
            ref: this.input,
            getValue: () => this.props.record.data[this.props.name] || "",
            parse: (v) => v,
        });
        this._sources = [
            {
                options: async (request) => {
                    if (!request || request.length < 3) return [];
                    try {
                        const result = await rpc("/cpq_transport/autocomplete", {
                            query: request,
                        });
                        return (result.suggestions || []).map((s) => ({
                            label: s.text,
                            onSelect: () => this.selectSuggestion(s),
                        }));
                    } catch (err) {
                        return [];
                    }
                },
                placeholder: "Searching for addresses...",
            },
        ];
    }

    get sources() {
        return this._sources;
    }

    async selectSuggestion(suggestion) {
        await this.props.record.update({ [this.props.name]: suggestion.text });
        // Auto-compute distance if both addresses are filled — one API call
        // per validated address pair, not per keystroke.
        const origin = this.props.record.data.origin_address;
        const destination = this.props.record.data.destination_address;
        if (origin && destination && this.props.record.resId) {
            try {
                await this.props.record.save();
                await this.orm.call(
                    "cpq.transport.wizard",
                    "action_compute_distance",
                    [this.props.record.resId]
                );
                await this.props.record.load();
            } catch (err) {
                // Auto-compute failed (API quota, no route, etc.) — user can
                // still click "Compute distance" manually to see the error.
                console.warn("cpq_transport auto-compute failed:", err);
            }
        }
    }
}

export const transportPlacesV2 = {
    ...charField,
    component: TransportPlacesAutocompleteV2,
    displayName: "Transport places autocomplete",
    supportedTypes: ["char"],
};

registry.category("fields").add("transport_places_v2", transportPlacesV2);
