# Retrieval A/B Benchmark (Top-5)

Legacy mode: semantic->exact->lemma (short-circuit)

Hybrid mode: semantic+exact+lemma merged by RRF

## Summary
- queries_total: 30
- top_k: 5
- queries_changed_top5: 30
- queries_changed_top5_rate: 1.0
- avg_overlap_at_5: 3.0667
- avg_before_latency_ms: 180.97
- avg_after_latency_ms: 184.47
- before_empty_results: 0
- after_empty_results: 0

## Example Queries (largest top-5 shifts)
### 1. нужен переход с r-keeper
- overlap@5: 1
- before_keys: pricing/pricing_integration_rkeeper_tis_2173, tis/retail_tax_return_307, tis/retail_tax_from_tis_276, tis/retail_tax_wrong_oked_264, tis/retail_tax_nds_after_278
- after_keys: tis/tis_nds_property_sale_310, support/support_migrate_beksar_1019, integrations/tis_1c_iiko_213, tis/retail_tax_return_307, tis/tis_to_too_596
- added_keys: integrations/tis_1c_iiko_213, support/support_migrate_beksar_1019, tis/tis_nds_property_sale_310, tis/tis_to_too_596
- removed_keys: pricing/pricing_integration_rkeeper_tis_2173, tis/retail_tax_from_tis_276, tis/retail_tax_nds_after_278, tis/retail_tax_wrong_oked_264

### 2. расскажите про Mini
- overlap@5: 1
- before_keys: pricing/pricing_mini_small_store_1814, pricing/pricing_mini_no_hardware_788, pricing/pricing_mini_includes_1884, pricing/pricing_upgrade_from_mini_1815, pricing/pricing_mini_no_inventory_1914
- after_keys: pricing/pricing_tariff_mini_427, products/products_wipon_mini_399, pricing/pricing_mini_no_hardware_788, pricing/pricing_upgrade_mini_standard_1224, pricing/pricing_wipon_mini_program_597
- added_keys: pricing/pricing_tariff_mini_427, pricing/pricing_upgrade_mini_standard_1224, pricing/pricing_wipon_mini_program_597, products/products_wipon_mini_399
- removed_keys: pricing/pricing_mini_includes_1884, pricing/pricing_mini_no_inventory_1914, pricing/pricing_mini_small_store_1814, pricing/pricing_upgrade_from_mini_1815

### 3. у меня 2 магазина, сейчас на Poster
- overlap@5: 1
- before_keys: features/features_second_store_account_1654, equipment/equipment_pos_duo_clothing_1817, products/products_clothing_chain_1605, equipment/equipment_second_screen_1538, equipment/equipment_kit_chain_1295
- after_keys: equipment/equipment_monoblock_recommendation_823, equipment/equipment_clothing_964, products/products_wipon_retail_multistore_1260, equipment/equipment_kit_chain_1295, equipment/equipment_beer_shop_960
- added_keys: equipment/equipment_beer_shop_960, equipment/equipment_clothing_964, equipment/equipment_monoblock_recommendation_823, products/products_wipon_retail_multistore_1260
- removed_keys: equipment/equipment_pos_duo_clothing_1817, equipment/equipment_second_screen_1538, features/features_second_store_account_1654, products/products_clothing_chain_1605

### 4. есть рассрочка?
- overlap@5: 2
- before_keys: pricing/pricing_installment_950, pricing/pricing_installment_program_equipment_1111, pricing/pricing_installment_1676, pricing/pricing_installment_equipment_1930, equipment/equipment_offer_list_1037
- after_keys: pricing/pricing_installment_950, pricing/pricing_installment_program_equipment_1111, pricing/pricing_installment_program_1275, pricing/pricing_equipment_installment_953, pricing/pricing_installment_tariff_951
- added_keys: pricing/pricing_equipment_installment_953, pricing/pricing_installment_program_1275, pricing/pricing_installment_tariff_951
- removed_keys: equipment/equipment_offer_list_1037, pricing/pricing_installment_1676, pricing/pricing_installment_equipment_1930

### 5. как вести инвентаризацию?
- overlap@5: 2
- before_keys: inventory/inventory_stocktaking_474, inventory/inventory_revision_001, inventory/inventory_loss_tracking_802, inventory/inventory_revision_673, inventory/inventory_revision_1504
- after_keys: inventory/inventory_stocktaking_474, inventory/inventory_revision_wipon_377, inventory/inventory_beginner_480, features/inventory, inventory/inventory_revision_673
- added_keys: features/inventory, inventory/inventory_beginner_480, inventory/inventory_revision_wipon_377
- removed_keys: inventory/inventory_loss_tracking_802, inventory/inventory_revision_001, inventory/inventory_revision_1504
