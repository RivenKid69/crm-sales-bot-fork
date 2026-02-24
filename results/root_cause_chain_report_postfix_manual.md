# Root Cause Chain Audit

## Headline
- Retrieval top-5 hit rate: 46 / 54 (85.2%)
- Retrieval pre-rerank@20 hit rate: 50 / 54 (92.6%)
- E2E factual pass rate: 37 / 40 (92.5%)

## Top Root Causes
- reranker_or_cutoff_regression: 4
- retrieval_recall_gap: 3
- empty_retrieval_context: 3
- orchestration_ranking_loss: 1

## Retrieval Failure Buckets
- reranker_or_cutoff_regression: 4
- retrieval_recall_gap: 3
- orchestration_ranking_loss: 1

## E2E Failure Buckets
- empty_retrieval_context: 3

## Sample Retrieval Misses
- [Pricing] цена за 5 точек
  root=retrieval_recall_gap expected=['pricing_multistore', 'pricing_5', 'tariffs']
  top5=['pricing/pricing_upgrade_path_by_points_2212', 'tis/tis_cost_622', 'pricing/pricing_two_locations_835', 'pricing/pricing_additional_point_roznica_2176', 'pricing/pricing_wipon_program_1214']
- [Pricing] стоимость на 10 касс
  root=retrieval_recall_gap expected=['tariffs', 'pricing_tariff', 'pricing_multistore']
  top5=['pricing/pricing_scanners_148', 'pricing/pricing_pro_kit_659', 'pricing/pricing_simple_cash_687', 'pricing/pricing_mini_small_shop_1397', 'pricing/pricing_standard_kit_606']
- [Pricing] почём самый дешёвый тариф?
  root=reranker_or_cutoff_regression expected=['tariffs', 'pricing_tariff_mini', 'products_wipon_mini']
  top5=['pricing/pricing_cheapest_1222', 'pricing/pricing_minimal_tariff_610', 'pricing/pricing_standard_detailed_1220', 'pricing/pricing_wipon_program_1214', 'equipment/equipment_kit_cheaper_1294']
- [Support] есть ли техническая поддержка 24/7?
  root=reranker_or_cutoff_regression expected=['support_sla', 'support_channel', 'help']
  top5=['support/support_response_time_001', 'support/support_weekend_001', 'support/support_working_hours_1523', 'support/support_weekend_available_001', 'support/support_weekend_hours_1687']
- [TIS] какой налоговый режим мне выбрать?
  root=reranker_or_cutoff_regression expected=['tis_retail', 'tis_earning', 'tis_too']
  top5=['support/support_tax_regime_choice_352', 'tis/retail_tax_start_date_246', 'tis/tis_2026_226', 'tis/tis_general_regime_danger_189', 'support/support_snr_vs_osn_explanation_332']
- [Tricky] мне нужна автоматизация магазина
  root=retrieval_recall_gap expected=['products_wipon', 'overview']
  top5=['products/products_grocery_store_916', 'regions/regions_oneday_consult_2086', 'integrations/integrations_kaspi_store_1052', 'products/products_almaty_full_1040', 'products/products_business_program_1008']
- [Tricky] а если у меня сеть магазинов?
  root=reranker_or_cutoff_regression expected=['faq_network', 'pricing_multistore', 'multistore']
  top5=['pricing/pricing_chain_stores_1228', 'products/products_retail_chain_651', 'products/products_small_shop_444', 'equipment/equipment_kit_chain_1295', 'products/products_chain_almaty_pro_1044']
- [Tricky] у нас 5 точек по Казахстану
  root=orchestration_ranking_loss expected=['regions_', 'coverage', 'pricing_multistore']
  top5=[]

## Sample E2E Fails
- kb15_offline_mode: empty_retrieval_context
  issues=["MISS: none of ['офлайн', 'оффлайн', 'без интернет', 'автоматическ', 'синхронизац'] found"]
  fact_keys=['stability/stability_offline_002', 'stability/stability_offline_check_721', 'stability/stability_internet_needed_616', 'stability/stability_internet_off_745', 'stability/stability_no_internet_675']
- kb20_multi_question: empty_retrieval_context
  issues=["MISS: none of ['168 000', '168000', '219 000', '219000', '100 000', '100000', 'комплект', 'Standard'] found"]
  fact_keys=['pricing/pricing_bundles_152', 'pricing/pricing_mini_store_equipment_1665', 'pricing/pricing_scanners_148', 'equipment/hardware', 'pricing/pricing_budget_100k_2085']
- w2_09_marketplaces: empty_retrieval_context
  issues=["MISS: none of ['Kaspi Магазин', 'kaspi магазин', 'Halyk Market', 'halyk market', 'Каспи Магазин', 'Халык Маркет', 'каспи магазин'] found"]
  fact_keys=['integrations/marketplaces', 'integrations/integrations_marketplaces_744', 'integrations/integrations_ozon_wildberries_722', 'products/products_wipon_retail_marketplaces_1257', 'integrations/integrations_online_store_631']
