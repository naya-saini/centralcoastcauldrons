Version 4 metrics

1. A time series chart of sales per potion by hour. These should be the actual potions you've made available for sale so far.
    SELECT
        DATE_TRUNC('hour', sold_at) AS sale_hour,
        potion_sku,
        SUM(quantity) AS potions_sold
    FROM potion_sales
    GROUP BY
        DATE_TRUNC('hour', sold_at),
        potion_sku
    ORDER BY
        sale_hour,
        potion_sku;

    For a simpler hourly comparison across all available potions:

    SELECT
        EXTRACT(HOUR FROM sold_at)::int AS hour_of_day,
        potion_sku,
        SUM(quantity) AS potions_sold
    FROM potion_sales
    GROUP BY
        EXTRACT(HOUR FROM sold_at),
        potion_sku
    ORDER BY
        hour_of_day,
        potion_sku;

2. A table of all barrel types, when the barrel type is offered, what liquid type it contains, and the cost per ml.
    SELECT
        sku,
        offered_at,
        potion_type,
        ml_per_barrel,
        price,
    ROUND(price::numeric / ml_per_barrel, 4) AS cost_per_ml
    FROM wholesale_barrels
    ORDER BY
        offered_at,
        sku;



3. Visualization(s) of what class, species, and level are purchasing what type of potion.
CLASS:
    SELECT
        customer_class,
        potion_sku,
        SUM(quantity) AS potions_sold
    FROM potion_sales
    GROUP BY
        customer_class,
        potion_sku
    ORDER BY
        customer_class,
        potions_sold DESC;

SPECIES:
    SELECT
        character_species,
        potion_sku,
        SUM(quantity) AS potions_sold
    FROM potion_sales
    GROUP BY
        character_species,
        potion_sku
    ORDER BY
        character_species,
        potions_sold DESC;

POTIONS:
    SELECT
        level,
        potion_sku,
        SUM(quantity) AS potions_sold
    FROM potion_sales
    GROUP BY
        level,
        potion_sku
    ORDER BY
        level,
        potion_sku;

4. An additional visualization of your choosing that tells you something the above three visualizations don't.
Gold spent per class
    SELECT
        customer_class,
        SUM(quantity * unit_price) AS gold_spent
    FROM potion_sales
    GROUP BY customer_class
    ORDER BY gold_spent DESC;