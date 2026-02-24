# Root Cause Chain Audit

## Headline
- Retrieval top-5 hit rate: 46 / 54 (85.2%)
- Retrieval pre-rerank@20 hit rate: 50 / 54 (92.6%)
- E2E factual pass rate: 31 / 40 (77.5%)

## Top Root Causes
- generation_grounding_loss_with_budget_pressure: 9
- reranker_or_cutoff_regression: 4
- retrieval_recall_gap: 3
- orchestration_ranking_loss: 1

## Retrieval Failure Buckets
- reranker_or_cutoff_regression: 4
- retrieval_recall_gap: 3
- orchestration_ranking_loss: 1

## E2E Failure Buckets
- generation_grounding_loss_with_budget_pressure: 9

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
- kb07_pos_prices: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['140 000', '140000', '140 тыс', '160 000', '160000', '160 тыс', '220 000', '220000', '220 тыс', '240 000', '240000', '240 тыс', '300 000', '300000', '300 тыс', '330 000', '330000', '330 тыс', '365 000', '365000', '365 тыс'] found"]
  fact_keys=['pricing/pricing_monoblocks_146', 'pricing/pricing_pos_premium_2185', 'equipment/equipment_specs_pos_premium_2142', 'pricing/pricing_pos_i5_monoblock_2209', 'pricing/pricing_wipon_5in1_2187']
- kb08_bundle_prices: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['168 000', '168000', '219 000', '219000'] found"]
  fact_keys=['equipment/equipment_combo_863', 'pricing/pricing_kit_pro_2184', 'equipment/equipment_kit_recommendation_821', 'equipment/equipment_combo_list_864', 'pricing/pricing_bundles_152']
- kb09_printers_scanners: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['15 000', '15000', '25 000', '25000', '10 000', '10000', '17 000', '17000'] found"]
  fact_keys=['pricing/pricing_printers_147', 'equipment/equipment_receipt_printers_1718', 'pricing/pricing_wp930z_2195', 'pricing/pricing_mini_store_equipment_1665', 'pricing/pricing_wpb930_2196']
- kb10_scales: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['100 000', '100000', '200 000', '200000', '100 тыс', '200 тыс'] found"]
  fact_keys=['pricing/pricing_scales_150', 'pricing/pricing_smart_scales_436', 'equipment/hardware', 'equipment/equipment_scales_spices_600', 'pricing/pricing_scales_rongta_438']
- kb11_installment: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['рассрочк', 'Kaspi', 'Каспи', '0-0-12', '12 месяц'] found"]
  fact_keys=[]
- w2_02_tax_forms: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['910', '913', '200'] found"]
  fact_keys=['fiscal/fiscal_tax_report_749', 'fiscal/fiscal_tax_reporting_633', 'tis/tis_tax_regime_225', 'support/support_no_accountant_760', 'fiscal/fiscal_tax_reports_682']
- w2_03_ofd_cost: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['1 400', '1400', '1 120', '1120', 'бесплатн', 'включен', 'входит'] found"]
  fact_keys=['fiscal/fiscal_ofd_charge_625', 'fiscal/fiscal_ofd_paid_1104', 'pricing/pricing_tariff_pro_430', 'fiscal/fiscal_ofd_only_1135', 'pricing/pricing_wipon_ofd_2209']
- w2_04_marking: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['маркировк', 'Data Matrix', 'data matrix', 'ISMET', 'ismet', 'Исмет'] found"]
  fact_keys=['fiscal/fiscal_marked_goods_1723', 'products/products_wipon_retail_marking_1258', 'integrations/integrations_marking_814', 'integrations/integrations_marking_618', 'integrations/integrations_marking_support_1167']
- w2_05_banks: generation_grounding_loss_with_budget_pressure
  issues=["MISS: none of ['Forte', 'Halyk', 'Kaspi', 'Jysan', 'Jýsan', 'BCC', 'форте', 'халык', 'каспи', 'жусан'] found"]
  fact_keys=['integrations/integrations_bank_terminals_1708', 'integrations/integrations_halyk_pos_1694', 'integrations/integrations_multi_acquiring_1085', 'integrations/integrations_bank_list_536', 'integrations/payments']
