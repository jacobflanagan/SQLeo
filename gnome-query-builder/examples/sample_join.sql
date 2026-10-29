-- Example Spark SQL shaped like the spike emitter (three-level UC names).
SELECT
  `customers`.`customer_id`,
  `customers`.`name`,
  `orders`.`order_id`,
  `orders`.`amount`
FROM `main`.`default`.`customers` AS `customers`
INNER JOIN `main`.`default`.`orders` AS `orders`
  ON `customers`.`customer_id` = `orders`.`customer_id`
LIMIT 100
