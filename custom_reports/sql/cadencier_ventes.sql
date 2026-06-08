-- ============================================================
-- CADENCIER STAT VENTES ARTICLES
-- Equivalent SQL de cadencier_sale.py/_get_report_data()
--
-- Paramètres :
--   %(year)s        → année entière (ex: 2026)
--   %(company_id)s  → ID société (ex: 1)
--   %(famille_ids)s → tableau d'IDs catégorie (ex: ARRAY[1,2,3])
--                     ou NULL pour tout inclure
--
-- Règles métier répliquées depuis Python :
--   - Produits type 'consu', actifs, cat_gestion IN (01,02,04,05,06,DI)
--   - Liés à la société via allowed_company_ids
--   - Statut C  → toujours inclus
--   - Statut D  → inclus seulement si au moins UN variant a stock > 0
--   - Autres statuts → exclus
--   - Tri : LOWER(code_famille), LOWER(code_article) (identique au Python)
--   - Date ventes : >= 1er jan | <= 31 déc minuit (comportement ORM Odoo)
--
-- ⚠ pvtc : list_price (HT). Le TTC réel (taxes['total_included'])
--   nécessite le moteur de taxes Odoo, non reproductible en SQL pur.
--
-- ⚠ Sous-totaux par famille : non inclus dans ce SQL (lignes plates).
--   Le Python intercale des lignes is_subtotal=True entre familles.
--   A calculer côté applicatif ou via ROLLUP si nécessaire.
-- ============================================================

WITH

-- ── 1. Stock agrégé au niveau du template ──────────────────
-- Python : any(v.qty_available > 0 for v in p.product_variant_ids)
-- → on agrège par tmpl_id pour vérifier qu'au moins 1 variant a du stock
stock_by_tmpl AS (
    SELECT
        pp.product_tmpl_id                AS tmpl_id,
        SUM(sq.quantity)                  AS qty_total
    FROM stock_quant sq
    JOIN stock_location sl  ON sl.id  = sq.location_id
    JOIN product_product pp ON pp.id  = sq.product_id
    WHERE sl.usage      = 'internal'
      AND sl.company_id = %(company_id)s
    GROUP BY pp.product_tmpl_id
),

-- ── 2. Produits éligibles ──────────────────────────────────
eligible AS (
    SELECT
        pp.id AS product_id,
        pt.id AS tmpl_id
    FROM product_product pp
    JOIN product_template pt ON pt.id = pp.product_tmpl_id
    -- Sociétés autorisées (allowed_company_ids)
    JOIN product_template_allowed_company_rel ptac
        ON ptac.product_tmpl_id = pt.id
       AND ptac.company_id      = %(company_id)s
    -- Catégorie de gestion X3
    JOIN product_category_x3 cgx ON cgx.id = pt.cat_gestion_id
    -- Statut par société
    LEFT JOIN product_company_status pcs
        ON pcs.product_id = pt.id
       AND pcs.company_id = %(company_id)s
    LEFT JOIN product_status ps ON ps.id = pcs.status_id
    -- Stock au niveau template (pour règle Statut D)
    LEFT JOIN stock_by_tmpl stk_rule ON stk_rule.tmpl_id = pt.id
    WHERE pt.type   = 'consu'
      AND pt.active = TRUE
      AND pp.active = TRUE
      AND cgx.name IN ('01', '02', '04', '05', '06', 'DI')
      -- Statut C toujours | Statut D seulement si stock template > 0
      AND (
          ps.code = 'C'
          OR (ps.code = 'D' AND COALESCE(stk_rule.qty_total, 0) > 0)
      )
      -- Filtre famille optionnel (NULL = toutes les familles)
      AND (%(famille_ids)s IS NULL OR pt.categ_id = ANY(%(famille_ids)s::int[]))
),

-- ── 3. Ventes Sale agrégées par produit et par mois ────────
-- Date : >= '%(year)s-01-01' AND <= '%(year)s-12-31'
-- (comportement ORM Odoo : <= date est converti à minuit 00:00:00)
sale_agg AS (
    SELECT
        sol.product_id,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 1  THEN sol.product_uom_qty ELSE 0 END) AS m01,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 2  THEN sol.product_uom_qty ELSE 0 END) AS m02,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 3  THEN sol.product_uom_qty ELSE 0 END) AS m03,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 4  THEN sol.product_uom_qty ELSE 0 END) AS m04,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 5  THEN sol.product_uom_qty ELSE 0 END) AS m05,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 6  THEN sol.product_uom_qty ELSE 0 END) AS m06,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 7  THEN sol.product_uom_qty ELSE 0 END) AS m07,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 8  THEN sol.product_uom_qty ELSE 0 END) AS m08,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 9  THEN sol.product_uom_qty ELSE 0 END) AS m09,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 10 THEN sol.product_uom_qty ELSE 0 END) AS m10,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 11 THEN sol.product_uom_qty ELSE 0 END) AS m11,
        SUM(CASE WHEN EXTRACT(MONTH FROM so.date_order AT TIME ZONE 'UTC') = 12 THEN sol.product_uom_qty ELSE 0 END) AS m12,
        SUM(sol.price_subtotal) AS ca,
        SUM(sol.margin)         AS margin
    FROM sale_order_line sol
    JOIN sale_order so ON so.id = sol.order_id
    WHERE so.state      IN ('sale', 'done')
      AND so.company_id  = %(company_id)s
      AND so.date_order >= (make_date(%(year)s, 1, 1))::timestamp
      AND so.date_order <  (make_date(%(year)s, 12, 31))::timestamp  -- <= 31 déc minuit = comportement ORM
      AND sol.product_id IN (SELECT product_id FROM eligible)
    GROUP BY sol.product_id
),

-- ── 4. Ventes POS agrégées par produit et par mois ─────────
pos_agg AS (
    SELECT
        pol.product_id,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 1  THEN pol.qty ELSE 0 END) AS m01,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 2  THEN pol.qty ELSE 0 END) AS m02,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 3  THEN pol.qty ELSE 0 END) AS m03,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 4  THEN pol.qty ELSE 0 END) AS m04,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 5  THEN pol.qty ELSE 0 END) AS m05,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 6  THEN pol.qty ELSE 0 END) AS m06,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 7  THEN pol.qty ELSE 0 END) AS m07,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 8  THEN pol.qty ELSE 0 END) AS m08,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 9  THEN pol.qty ELSE 0 END) AS m09,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 10 THEN pol.qty ELSE 0 END) AS m10,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 11 THEN pol.qty ELSE 0 END) AS m11,
        SUM(CASE WHEN EXTRACT(MONTH FROM po.date_order AT TIME ZONE 'UTC') = 12 THEN pol.qty ELSE 0 END) AS m12,
        SUM(pol.price_subtotal) AS ca,
        -- margin = (price_subtotal * sign) - total_cost  (sign=-1 si remboursement)
        SUM(CASE WHEN po.is_refund THEN -pol.price_subtotal ELSE pol.price_subtotal END - pol.total_cost) AS margin
    FROM pos_order_line pol
    JOIN pos_order po ON po.id = pol.order_id
    WHERE po.state      IN ('done', 'paid', 'invoiced')
      AND po.company_id  = %(company_id)s
      AND po.date_order >= (make_date(%(year)s, 1, 1))::timestamp
      AND po.date_order <  (make_date(%(year)s, 12, 31))::timestamp
      AND pol.product_id IN (SELECT product_id FROM eligible)
    GROUP BY pol.product_id
),

-- ── 5. Stock disponible par variant (pour affichage st_disp) ─
-- Python : p.with_company(company).qty_available (par variant)
stock_variant AS (
    SELECT sq.product_id,
           ROUND(SUM(sq.quantity)::NUMERIC, 2) AS qty_available
    FROM stock_quant sq
    JOIN stock_location sl ON sl.id = sq.location_id
    WHERE sl.usage      = 'internal'
      AND sl.company_id = %(company_id)s
    GROUP BY sq.product_id
),

-- ── 6. Quantité maxi (premier orderpoint de la société) ─────
-- Python : orderpoint.product_max_qty (limit=1 sur la société)
orderpoints AS (
    SELECT DISTINCT ON (pp.product_tmpl_id)
        pp.product_tmpl_id AS tmpl_id,
        swo.product_max_qty
    FROM stock_warehouse_orderpoint swo
    JOIN product_product pp ON pp.id = swo.product_id
    WHERE swo.company_id = %(company_id)s
    ORDER BY pp.product_tmpl_id, swo.id
),

-- ── 7. Réceptions en attente (draft + assigned) ─────────────
-- Python : stock.move state IN ('draft','assigned'), incoming, société
pending_rec AS (
    SELECT pp.product_tmpl_id      AS tmpl_id,
           SUM(sm.product_uom_qty) AS pending_qty
    FROM stock_move sm
    JOIN product_product   pp  ON pp.id  = sm.product_id
    JOIN stock_picking      sp  ON sp.id  = sm.picking_id
    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
    WHERE spt.code       = 'incoming'
      AND sm.state      IN ('draft', 'assigned')
      AND sm.company_id  = %(company_id)s
    GROUP BY pp.product_tmpl_id
)

-- ── RÉSULTAT FINAL (lignes produits plates, sans sous-totaux) ─
-- Tri identique au Python : LOWER(code_famille), LOWER(code_article)
SELECT
    COALESCE(pp.default_code, '')                                 AS code,
    pt.name                                                       AS designation,
    COALESCE(ps.code, '')                                         AS sta,
    pc.name                                                       AS famille,
    pc.code                                                       AS code_famille,
    COALESCE(stk.qty_available, 0)                                AS st_disp,
    COALESCE(op.product_max_qty, 0)                               AS maxi,
    ROUND(COALESCE(pr.pending_qty, 0)::NUMERIC, 2)                AS cmd,

    -- % Marge = (margin_sale + margin_pos) / (ca_sale + ca_pos) * 100
    CASE
        WHEN COALESCE(sa.ca, 0) + COALESCE(pa.ca, 0) > 0
        THEN ROUND(
                 (COALESCE(sa.margin, 0) + COALESCE(pa.margin, 0))
                 / (COALESCE(sa.ca, 0) + COALESCE(pa.ca, 0)) * 100,
             2)
        ELSE 0
    END                                                           AS marg_pct,

    -- ⚠ pvtc = list_price (HT). Le TTC réel (taxes['total_included'])
    --   nécessite le moteur de taxes Odoo.
    pt.list_price                                                 AS pvtc,

    -- Quantités mensuelles Sale + POS
    ROUND((COALESCE(sa.m01,0) + COALESCE(pa.m01,0))::NUMERIC, 2) AS jan,
    ROUND((COALESCE(sa.m02,0) + COALESCE(pa.m02,0))::NUMERIC, 2) AS fev,
    ROUND((COALESCE(sa.m03,0) + COALESCE(pa.m03,0))::NUMERIC, 2) AS mar,
    ROUND((COALESCE(sa.m04,0) + COALESCE(pa.m04,0))::NUMERIC, 2) AS avr,
    ROUND((COALESCE(sa.m05,0) + COALESCE(pa.m05,0))::NUMERIC, 2) AS mai,
    ROUND((COALESCE(sa.m06,0) + COALESCE(pa.m06,0))::NUMERIC, 2) AS juin,
    ROUND((COALESCE(sa.m07,0) + COALESCE(pa.m07,0))::NUMERIC, 2) AS jlt,
    ROUND((COALESCE(sa.m08,0) + COALESCE(pa.m08,0))::NUMERIC, 2) AS aot,
    ROUND((COALESCE(sa.m09,0) + COALESCE(pa.m09,0))::NUMERIC, 2) AS spt,
    ROUND((COALESCE(sa.m10,0) + COALESCE(pa.m10,0))::NUMERIC, 2) AS oct,
    ROUND((COALESCE(sa.m11,0) + COALESCE(pa.m11,0))::NUMERIC, 2) AS nov,
    ROUND((COALESCE(sa.m12,0) + COALESCE(pa.m12,0))::NUMERIC, 2) AS dec,

    -- Total annuel = somme des 12 mois
    ROUND((
        COALESCE(sa.m01,0) + COALESCE(pa.m01,0) +
        COALESCE(sa.m02,0) + COALESCE(pa.m02,0) +
        COALESCE(sa.m03,0) + COALESCE(pa.m03,0) +
        COALESCE(sa.m04,0) + COALESCE(pa.m04,0) +
        COALESCE(sa.m05,0) + COALESCE(pa.m05,0) +
        COALESCE(sa.m06,0) + COALESCE(pa.m06,0) +
        COALESCE(sa.m07,0) + COALESCE(pa.m07,0) +
        COALESCE(sa.m08,0) + COALESCE(pa.m08,0) +
        COALESCE(sa.m09,0) + COALESCE(pa.m09,0) +
        COALESCE(sa.m10,0) + COALESCE(pa.m10,0) +
        COALESCE(sa.m11,0) + COALESCE(pa.m11,0) +
        COALESCE(sa.m12,0) + COALESCE(pa.m12,0)
    )::NUMERIC, 2)                                                AS total,

    -- Champs internes (utilisés pour les sous-totaux applicatifs)
    COALESCE(sa.ca, 0) + COALESCE(pa.ca, 0)                      AS _ca,
    COALESCE(sa.margin, 0) + COALESCE(pa.margin, 0)              AS _margin

FROM eligible e
JOIN product_product   pp  ON pp.id     = e.product_id
JOIN product_template  pt  ON pt.id     = e.tmpl_id
JOIN product_category  pc  ON pc.id     = pt.categ_id
LEFT JOIN product_company_status pcs ON pcs.product_id = pt.id AND pcs.company_id = %(company_id)s
LEFT JOIN product_status         ps  ON ps.id           = pcs.status_id
LEFT JOIN sale_agg     sa  ON sa.product_id  = pp.id
LEFT JOIN pos_agg      pa  ON pa.product_id  = pp.id
LEFT JOIN stock_variant stk ON stk.product_id = pp.id
LEFT JOIN orderpoints  op  ON op.tmpl_id      = pt.id
LEFT JOIN pending_rec  pr  ON pr.tmpl_id      = pt.id

-- Tri identique au Python : key=lambda p: ((categ.code or '').lower(), (default_code or '').lower())
ORDER BY LOWER(COALESCE(pc.code, '')), LOWER(COALESCE(pp.default_code, ''));
