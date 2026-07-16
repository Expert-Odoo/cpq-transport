# cpq_transport — corrections apprises pendant le développement

## V1 (scaffold initial — 05/07/2026)

### Bugs Odoo 19 découverts pendant l'implémentation

1. **`--xmlrpc-port` supprimé en V19** — utiliser `--http-port` pour les tests via subprocess sur port dédié (8099).
2. **`models.NewId` n'existe plus dans le namespace `odoo.models`** — utiliser `isinstance(self.id, int)` pour tester si un enregistrement est sauvegardé. Un vrai id est un int, un id de nouveau record (NewId) ne l'est pas.
3. **`res.config.settings.view.form` (sale)** — le block Pricing a l'id `pricing_setting_container` (pas `sale_pricing_setting_container` comme dans d'autres modules Odoo).
4. **`sale.order.currency_id`** — computed depuis pricelist en V19. Pour forcer une devise dans les tests, créer une pricelist avec la devise cible et l'assigner au sale.order via `pricelist_id`. `create({currency_id: X})` ne suffit pas.
5. **Champs `required=True` sur wizard** — poser sur la vue XML (`required="1"`) plutôt que sur le champ Python, sinon impossible d'instancier le wizard programmatiquement quand certaines valeurs viennent après l'ouverture.

### Décisions actées

- Transport = prestation forfaitaire → `product_uom_qty` forcé à 1 dans `action_validate`.
- Pas de cache d'itinéraires en V1 (ROI faible, ira dans `cpq_transport_rules`).
- Pas de modèle `cpq.transport.product` : simple flag `is_transport` sur `product.template`.
- Adresses en texte libre géocodable (compatible Google Maps Distance Matrix).
- `state` du wizard (`draft` / `computed` / `stale`) gouverne la visibilité des boutons Valider / Recalculer.

### Test T15 (tour test HttpCase) — à faire

Non implémenté en V1. À ajouter avant publication App Store pour vérifier :
- Visibilité du bouton "Configurer le transport" uniquement sur les lignes `is_transport`.
- Ouverture correcte de la modale.
- Blocage de Valider tant que la distance n'a pas été calculée.

### Migration Distance Matrix (Legacy) → Routes API (Compute Route Matrix)

Google a marqué `maps.googleapis.com/maps/api/distancematrix` comme **Legacy** (juillet 2026). Migration effectuée avant publication App Store pour éviter que les nouveaux clients découvrant le module ne tombent sur une API deprecated côté Google Cloud Console.

**Différences de l'endpoint** :
- URL : `https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix`
- Méthode : POST avec body JSON (l'ancien était GET avec query params)
- Auth : header `X-Goog-Api-Key` (pas de `key=` dans l'URL)
- Header **obligatoire** `X-Goog-FieldMask` — sans lui, la réponse est vide ou incomplète.
- Adresses : `{"waypoint": {"address": "..."}}` en texte libre (accepté comme sur Distance Matrix).

**Différences de la réponse** :
- Réponse = array JSON direct (pas un dict avec `rows.elements`).
- Distance dans `distanceMeters` (int, mètres) au lieu de `distance.value`.
- Statut par élément via `condition` (`ROUTE_EXISTS` / `ROUTE_NOT_FOUND`) et objet `status` (google.rpc.Status : `code=0` = OK).
- Erreurs globales via `HTTPError` HTTP (401/403 = REQUEST_DENIED, 429 = OVER_QUERY_LIMIT, 400 = INVALID_REQUEST).

**Côté Google Cloud Console** : les clients doivent activer **Routes API** (pas Distance Matrix API) sur leur projet.

**Facturation** : Routes API est facturée légèrement différemment de Distance Matrix Legacy. Le crédit 200 $/mois couvre toujours l'usage devis typique. Tarif "Basic" ≈ 5 $/1000 requêtes.

### Refactor : cpq.transport.product (pattern cpq_window_door)

Le CDC initial avait décidé de ne pas créer de modèle `cpq.transport.product` (§7 de l'ARCHITECTURE) en jugeant qu'un simple flag `is_transport` sur `product.template` suffirait. **Décision révisée** : le pattern des autres modules CPQ (produit configurable déclaré séparément) est plus approprié pour :
- Cohérence UX avec la gamme CPQ Expodo
- Point d'entrée clair via le menu "Transport services"
- Extensibilité pour `cpq_transport_rules` (règles attachées au produit configurable)
- Défauts par produit (`default_price_per_km`, `origin_default`) avec fallback vers Settings

**Impact code** :
- Nouveau modèle `cpq.transport.product` avec M2o 1-1 vers `product.template`
- Flag `is_transport` retiré de `product.template` — computed depuis la recherche `cpq.transport.product`
- Smart button "🚚 Transport" sur l'en-tête devis (compteur + sélecteur multi-lignes)
- `cpq.transport.line.selector` pour choisir la ligne à configurer quand plusieurs lignes transport existent
- Menu Transport services pointe vers `cpq.transport.product` (pas vers product.template filtré)

### Odoo 19 : `_sql_constraints` remplacé par `models.Constraint`

Warning V19 explicite au chargement : « `Model attribute '_sql_constraints' is no longer supported, please define model.Constraint on the model.` »

**Ancienne syntaxe (silencieusement ignorée en V19)** :
```python
_sql_constraints = [
    ("name_uniq", "unique(field_id)", "Message"),
]
```

**Nouvelle syntaxe V19** :
```python
_name_uniq = models.Constraint(
    "UNIQUE(field_id)",
    "Message",
)
```

- Le nom du membre Python (`_name_uniq`) devient le suffixe du nom de la contrainte SQL (`<table>_<suffix>`).
- La contrainte SQL est bien créée en base après update — vérifiable via `SELECT conname FROM pg_constraint WHERE conrelid = '<table>'::regclass`.
- Pattern trouvé dans plusieurs modèles standards : `res_users._login_key`, `res_currency._unique_name`, `ir_model.model._obj_name_uniq`, etc.

### Odoo garde les anciennes valeurs de champs non redéclarés en XML

Découvert pendant le test UI end-to-end : après refactor du modèle sous-jacent d'une `ir.actions.act_window` (passage de `product.template` filtré à `cpq.transport.product`), le domain `[('is_transport', '=', True)]` restait présent en base, provoquant un `KeyError: 'is_transport'` au chargement de la vue.

**Cause** : sans `<field name="domain">...</field>` explicite dans le XML, Odoo ne touche pas au champ en base lors d'un update de module — il garde la valeur précédente.

**Fix** : toujours déclarer explicitement les champs `domain` et `context` sur les actions, même vides (`[]` et `{}`), pour garantir un état propre après refactor et sur les nouvelles installations.

```xml
<record id="action_transport_products" model="ir.actions.act_window">
    <field name="name">Transport services</field>
    <field name="res_model">cpq.transport.product</field>
    <field name="view_mode">kanban,list,form</field>
    <field name="domain">[]</field>       <!-- explicite pour ne pas hériter d'anciennes valeurs -->
    <field name="context">{}</field>      <!-- idem -->
    <field name="help" type="html">...</field>
</record>
```

### Test end-to-end validé (parcours utilisateur complet)

Testé via Claude for Chrome sur `odoo19-pictanovo-dev` port 8033 :
1. Menu Transport (CPQ) visible dans le dashboard.
2. Création d'un `cpq.transport.product` avec produit Odoo lié + `default_price_per_km=1.50` + `origin_default`.
3. Devis avec une ligne de ce produit : bouton "⚙ Configure transport" affiché.
4. Smart button "🚚 Transport" sur l'en-tête après save.
5. Wizard pré-rempli avec les defaults du `cpq.transport.product`.
6. Google Routes API répond : Paris → Lyon = 482.91 km (vraie API, vraie clé).
7. State passe à `computed`, boutons Validate + Recompute apparaissent.
8. Validate met à jour `price_unit=724.37 €`, `product_uom_qty=1`, description = summary.
9. Summary affiché : « 10 rue de Paris, 75001 Paris → Lyon, France · One-way · 482.91 km · 1.50 €/km ».

### Icône dashboard non rafraîchie après remplacement de `static/description/icon.png`

Symptôme : après avoir remplacé l'icône source du module, le dashboard Odoo continue d'afficher l'ancienne (ou le cube générique).

**Cause** : `ir.ui.menu.web_icon_data` est un champ **stocké** calculé une seule fois au moment où le menu root est créé (via `web_icon = "module_name,static/description/icon.png"`). Ni `-u module_name` ni un restart container ne le recalculent — Odoo considère que l'icône n'a pas changé au niveau XML.

**Fix** (une commande shell suffit) :

```python
menus = env['ir.ui.menu'].search([('web_icon', 'like', 'MODULE_NAME,%')])
for m in menus:
    m.web_icon = m.web_icon   # réassignation → recompute web_icon_data
env.cr.commit()
```

Puis Ctrl+Shift+R côté navigateur.

**Vérification** : `mod.icon_image` (sur `ir.module.module`) contient bien la nouvelle image (correcte), mais `menu.web_icon_data` reste bloqué sur l'ancienne. C'est le second qu'utilise le dashboard.

**Prévention pour les prochains modules** : générer l'icône en ≥ 512×512 dès le départ. Les icônes < 256×256 sont rendues pixelisées par Odoo (ratio de 4× vs les 128px cibles de rendu).
