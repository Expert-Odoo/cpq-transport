# cpq_transport — Cadrage complet

Module : **cpq_transport** (base gratuite LGPL-3)
Add-on payant prévu : **cpq_transport_rules** (paliers de prix, majorations, zones — cadrage séparé)

Dépendances : `sale_management`, `product`. Aucune dépendance à un `cpq_base`.

---

## §0 — Parcours utilisateur (obligatoire avant tout code)

### Persona
Commercial qui établit un devis contenant une prestation de livraison / transport dont le prix dépend de la distance réelle entre deux adresses.

### Parcours nominal (aller simple)

| Étape | Écran | Action utilisateur | Réaction Odoo |
|---|---|---|---|
| 1 | Devis brouillon | Ajoute une ligne, sélectionne un produit marqué `is_transport` | La ligne affiche un bouton **⚙ Configurer le transport** ; le prix unitaire reste à 0 tant que non configuré |
| 2 | Ligne devis | Clique sur **⚙ Configurer le transport** | Une fenêtre modale s'ouvre (wizard `cpq.transport.wizard`) |
| 3 | Fenêtre config | Saisit adresse départ (texte libre), adresse arrivée (texte libre), choisit type trajet (aller simple / aller-retour), prix/km pré-rempli avec la valeur par défaut des Settings | Aucune action serveur, saisie locale |
| 4 | Fenêtre config | Clique sur **📍 Calculer la distance** | Appel Google Maps Distance Matrix ; distance affichée en km (2 décimales) ; prix total calculé et affiché en lecture seule |
| 5 | Fenêtre config | Clique sur **Valider** | La `cpq.transport.config` est créée/mise à jour et liée à la ligne ; le `price_unit` de la ligne devis est mis à jour ; la fenêtre se ferme ; le récapitulatif s'affiche sous la ligne (« Paris → Lyon · A/R · 465 km · 2,00 €/km ») |
| 6 | Devis | Le total du devis est recalculé automatiquement (mécanisme standard Odoo) | — |

### Parcours de modification
- L'utilisateur rouvre le wizard via le même bouton → tous les champs sont pré-remplis avec la config existante.
- S'il change une adresse ou le type de trajet, un warning apparaît : *« La distance doit être recalculée »* ; le bouton **Valider** est désactivé tant que **📍 Calculer la distance** n'a pas été relancé.

### Parcours d'erreur
- Clé API absente → message d'erreur clair pointant vers *Paramètres → Ventes → Transport*.
- Adresse introuvable → l'API renvoie `ZERO_RESULTS` → message *« Adresse introuvable : {adresse} »*, distance non enregistrée, `price_unit` inchangé.
- Quota dépassé → `OVER_QUERY_LIMIT` → message explicite ; suggestion d'attendre ou de vérifier le compte Google Cloud.
- Ligne non sauvegardée (id temporaire) → `UserError` demandant de sauvegarder le devis d'abord (comme `cpq_window_door`).

### Règles UI
- Bouton **⚙ Configurer le transport** visible **uniquement** si `product_id.is_transport = True`.
- Récapitulatif affiché en dessous de la description dans la vue ligne (champ `transport_summary` en lecture seule).
- Icône ✓ / ○ dans le sélecteur si plusieurs lignes transport sur le même devis (cohérence avec `cpq_window_door`).

---

## §1 — Modèles de données

### `cpq.transport.config` (nouveau modèle)
Instance de configuration liée à une ligne de devis (1 config = 1 ligne).

| Champ | Type | Notes |
|---|---|---|
| `sale_line_id` | Many2one → `sale.order.line`, required, ondelete=cascade | Lien inverse |
| `origin_address` | Char, required | Texte libre géocodable par Google |
| `destination_address` | Char, required | Idem |
| `trip_type` | Selection `[('one_way', 'Aller simple'), ('round_trip', 'Aller-retour')]`, default `one_way`, required | |
| `price_per_km` | Monetary, required | Devise = `currency_id` (voir Settings) |
| `distance_km` | Float, readonly, digits=(10,2) | Rempli par le calcul API |
| `computed_price` | Monetary, compute (stocké) | `distance_km × price_per_km × (2 si round_trip)` |
| `currency_id` | Many2one → `res.currency` | Related sur `sale_line_id.order_id.currency_id` |
| `last_computed_at` | Datetime, readonly | Horodatage du dernier appel API réussi |
| `is_stale` | Boolean, compute (non stocké) | True si adresse/trip_type modifiés depuis `last_computed_at` |
| `summary` | Char, compute (stocké) | « Paris → Lyon · A/R · 465 km · 2,00 €/km » |

**Pas de modèle `cpq.transport.product`** : le CDC ne configure rien de spécifique au produit — seul un flag `is_transport` sur `product.template` suffit. Cohérent avec le principe *KISS* et évite un modèle vide qui n'apporterait aucune valeur.

### `sale.order.line` (héritage)
| Champ | Type | Notes |
|---|---|---|
| `is_transport` | Boolean, compute stocké | Depuis `product_id.product_tmpl_id.is_transport` |
| `transport_config_id` | Many2one → `cpq.transport.config`, ondelete=set null, copy=False | Config liée |
| `transport_summary` | Char, related `transport_config_id.summary`, store=True | Affichage vue ligne |

### `product.template` (héritage)
| Champ | Type | Notes |
|---|---|---|
| `is_transport` | Boolean, default False | Case à cocher dans l'onglet Ventes du produit |

### `res.config.settings` (héritage — Settings généraux)
| Champ | Type | Notes |
|---|---|---|
| `transport_gmaps_api_key` | Char | Stocké dans `ir.config_parameter` `cpq_transport.gmaps_api_key` |
| `transport_default_price_per_km` | Monetary | Stocké dans `ir.config_parameter` `cpq_transport.default_price_per_km` |
| `transport_currency_id` | Many2one → `res.currency` | Stocké dans `ir.config_parameter` `cpq_transport.currency_id` |

**Note devise** : la devise du prix/km affichée dans le wizard = celle du devis (`sale_order.currency_id`) pour cohérence. Le paramètre `transport_currency_id` des settings sert uniquement à typer le champ Monetary dans la vue Settings. Le `price_per_km` par défaut est copié tel quel (l'utilisateur peut le modifier ligne par ligne).

---

## §2 — Wizard `cpq.transport.wizard` (TransientModel)

Champs copiés de `cpq.transport.config` + :
- `state` selection `[('draft', 'Saisie'), ('computed', 'Distance calculée'), ('stale', 'À recalculer')]` pilote la visibilité du bouton Valider (invisible sauf en `computed`).

Actions :
- `action_compute_distance()` : appel Google Maps Distance Matrix → remplit `distance_km` → passe en `computed`.
- `action_validate()` : crée/met à jour la `cpq.transport.config`, met à jour `sale_line_id.price_unit` = `computed_price / product_uom_qty` (attention à la quantité !) — décision : forcer `product_uom_qty = 1` sur les lignes transport (le prix est TTC forfaitaire), ou diviser par la quantité. **À trancher.**

---

## §3 — Service API Google Maps

Fichier : `models/gmaps_service.py` — classe utilitaire (pas un modèle Odoo).

```python
class GoogleMapsService:
    ENDPOINT = "https://maps.googleapis.com/maps/api/distancematrix/json"

    @classmethod
    def get_distance_km(cls, origin, destination, api_key):
        """Retourne (distance_km: float, status: str, error_msg: str|None)."""
        # timeout 10s, mode=driving, units=metric
```

- Timeout 10s.
- Gestion des statuts `OK`, `ZERO_RESULTS`, `OVER_QUERY_LIMIT`, `REQUEST_DENIED`, `INVALID_REQUEST`.
- Journalisation `_logger.info` du couple (origin, destination) sans la clé API.
- **Pas de cache** dans le module de base (les adresses varient beaucoup, ROI faible pour la complexité ajoutée). Le cache éventuel ira dans `cpq_transport_rules`.

---

## §4 — Points d'extension UI (xpath)

| Vue | xpath | Contenu |
|---|---|---|
| `sale.view_order_form` | `//field[@name='order_line']/list/field[@name='price_unit']` position after | Bouton `action_configure_transport` (`invisible="not is_transport"`) |
| `sale.view_order_form` | Même endroit | Champ `transport_summary` readonly (`invisible="not is_transport"`) |
| `product.product_template_form_view` | `//page[@name='sales']` | Case à cocher `is_transport` |
| `sale.res_config_settings_view_form` | `//div[@id='sale_pricing_setting_container']` position after | Bloc Settings « Transport » |

**Risque collision** : `cpq_window_door` ajoute déjà un bouton `action_configure_cpq` sur la ligne devis. Vérifier que les xpath ciblent la même position — ils vont probablement cohabiter (deux boutons visibles selon le type de produit). Pas de conflit fonctionnel, l'un est piloté par `is_cpq`, l'autre par `is_transport`.

---

## §5 — Sécurité

- `ir.model.access.csv` : `cpq.transport.config` en RWCU pour `sales_team.group_sale_salesman`, lecture pour `base.group_user`.
- Pas de règle d'enregistrement multi-société (V1). À réévaluer si un client le demande.

---

## §6 — Cas de test (TransactionCase + 1 HttpCase)

Fichier : `tests/test_cpq_transport.py`

Constante : `DELTA = 0.01` (précision à 1 cm sur les km).

| ID | Nom | Setup | Action | Attendu |
|---|---|---|---|---|
| T01 | `test_is_transport_flag_propagates` | Produit avec `is_transport=True` | Ajout ligne devis | `line.is_transport = True` |
| T02 | `test_compute_price_one_way` | config avec distance=100, price_per_km=2, trip=one_way | Trigger compute | `computed_price = 200.0` |
| T03 | `test_compute_price_round_trip` | Idem, trip=round_trip | Trigger compute | `computed_price = 400.0` |
| T04 | `test_summary_format` | Config Paris→Lyon 465km A/R 2€/km | Trigger compute | `summary = "Paris → Lyon · A/R · 465,00 km · 2,00 €/km"` |
| T05 | `test_is_stale_after_address_change` | Config validée, `last_computed_at` set | Modifier `origin_address` | `is_stale = True` |
| T06 | `test_validate_updates_line_price` | Wizard en state=computed, distance=100, price_per_km=2, one_way | `action_validate` | `sale_line.price_unit = 200.0` |
| T07 | `test_default_price_per_km_from_settings` | `ir.config_parameter` = 1.5 | Créer une nouvelle config | `price_per_km = 1.5` par défaut |
| T08 | `test_zero_results_raises_userwarning` | Mock `GoogleMapsService.get_distance_km` → `('ZERO_RESULTS', ...)` | `action_compute_distance` | `UserError` avec message localisé |
| T09 | `test_missing_api_key_raises_userwarning` | Aucun `ir.config_parameter` | `action_compute_distance` | `UserError` explicite |
| T10 | `test_currency_follows_order` | Devis en USD | Créer config | `currency_id = USD` |
| T11 | `test_line_without_transport_no_button` | Produit `is_transport=False` | Vérifier vue rendue | Bouton absent (via `_view_get` + parsing XML) |
| T12 | `test_delete_config_on_line_delete` | Ligne + config existante | Supprimer la ligne | Config supprimée (ondelete=cascade) |
| T13 | `test_stale_blocks_validate` | Wizard en state=stale | `action_validate` | `UserError` « Recalculer la distance d'abord » |
| T14 | `test_gmaps_service_ok_mock` | Mock httpx retournant payload OK | `get_distance_km('Paris', 'Lyon', 'FAKE')` | `(465.0, 'OK', None)` |

**Tour test** (T15, HttpCase) : parcours complet UI — création devis, ajout produit transport, ouverture wizard, saisie adresses, calcul, validation. À implémenter en dernier une fois le reste stable.

Tous les appels réseau réels **mockés** dans les tests via `unittest.mock.patch` sur `GoogleMapsService.get_distance_km`.

---

## §7 — Décisions déjà tranchées (à ne pas reconsidérer)

1. **API cartographique** : Google Maps Distance Matrix (validé Foued).
2. **Stockage** : modèle séparé `cpq.transport.config` + Many2one depuis `sale.order.line` (pattern `cpq_window_door`, validé Foued).
3. **Format adresses** : texte libre (Char) géocodé côté Google (validé Foued).
4. **Pas de `cpq_base`** : module autonome sur `sale_management` + `product`.
5. **Pas de cache** dans la base — ira dans `cpq_transport_rules`.
6. **Pas de modèle `cpq.transport.product`** : simple flag `is_transport` sur `product.template`.
7. **Freemium** : ce module = base LGPL gratuite. `cpq_transport_rules` = add-on payant OPL-1 (cadré séparément).

---

## §8 — Points à trancher AVANT scaffolding

1. **Quantité de la ligne de devis** : forcer `product_uom_qty = 1` (transport = prestation forfaitaire), ou diviser le prix total par la qté ? Recommandation : **forcer à 1** et rendre le champ readonly quand `is_transport=True`.
2. **Nom exact du bouton** : « Configurer le transport » ou « 📍 Calculer transport » ? Recommandation : cohérence avec `cpq_window_door` → « ⚙ Configurer le transport ».
3. **Type de produit Odoo** : `service` par défaut ? À forcer via onchange sur `is_transport` ?
4. **Provider fallback** : prévoir dès la V1 une abstraction pour switcher facilement vers OpenRouteService/HERE dans une V2 ? Recommandation : oui, `GoogleMapsService` avec interface identique = surcoût minime pour flexibilité future.

---

## Structure de fichiers cible

```
cpq_transport/
├── __init__.py
├── __manifest__.py
├── security/
│   └── ir.model.access.csv
├── models/
│   ├── __init__.py
│   ├── cpq_transport_config.py
│   ├── sale_order_line.py
│   ├── product_template.py
│   ├── res_config_settings.py
│   └── gmaps_service.py
├── wizard/
│   ├── __init__.py
│   └── cpq_transport_wizard.py
├── views/
│   ├── cpq_transport_config_views.xml
│   ├── product_template_views.xml
│   ├── sale_order_views.xml
│   └── res_config_settings_views.xml
├── data/
│   └── ir_config_parameter_data.xml   (valeurs par défaut vides — pas de clé API démo)
├── i18n/
│   └── fr.po
├── tests/
│   ├── __init__.py
│   └── test_cpq_transport.py
├── static/description/
│   ├── icon.png
│   ├── banner.png
│   └── index.html
├── CHANGELOG.md
├── ARCHITECTURE.md          (ce document)
└── known_corrections.md     (vide au départ)
```

Aucun `demo/` : le module doit fonctionner sur installation propre sans données démo (règle apprise sur `cpq_window_door`).
