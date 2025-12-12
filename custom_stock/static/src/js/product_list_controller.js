/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(ListController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel === 'product.template') {
            this._checkCreateAccess();
        }
    },
    
    async _checkCreateAccess() {
        try {
            const result = await this.rpc({
                model: 'product.template',
                method: 'check_access_create_product',
                args: [],
            });
            
            if (!result) {
                // Masquer le bouton de création
                this.canCreate = false;
            }
        } catch (error) {
            console.error('Erreur lors de la vérification des droits:', error);
        }
    },
});