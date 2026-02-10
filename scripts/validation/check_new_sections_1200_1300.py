#!/usr/bin/env python3
"""
Тест точности новых секций 1200-1300.

Для каждой секции минимум 5 уникальных запросов, имитирующих клиента.
Проверяем, что retriever находит нужную секцию в топ-1.

Запуск: python3 check_new_sections_1200_1300.py
"""

import sys
import os
import time
from typing import List, Tuple, Dict
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.knowledge.retriever import CascadeRetriever, reset_retriever

# =============================================================================
# Тестовые запросы для новых секций 1200-1300
# Формат: (запрос, ожидаемый topic, описание)
# =============================================================================

TEST_QUERIES: List[Tuple[str, str, str]] = [
    # =========================================================================
    # REGIONS 1200-1211 (12 секций × 5 запросов = 60 запросов)
    # =========================================================================

    # regions_onsite_petropavlovsk_1200
    ("в петропавловске можете установить кассу?", "regions_onsite_petropavlovsk_1200", "петропавловск установка"),
    ("петропавловск выезжаете для настройки?", "regions_onsite_petropavlovsk_1200", "петропавловск выезд"),
    ("приедете ли в петропавл установить оборудование?", "regions_onsite_petropavlovsk_1200", "петропавл сокращ"),
    ("северный казахстан установка кассы на месте", "regions_onsite_petropavlovsk_1200", "СКО"),
    ("ско область выезд мастера есть?", "regions_onsite_petropavlovsk_1200", "СКО мастер"),

    # regions_onsite_aktau_1201
    ("актау можете приехать поставить оборудование?", "regions_onsite_aktau_1201", "актау приехать"),
    ("в мангистау есть выезд специалиста?", "regions_onsite_aktau_1201", "мангистау"),
    ("актаудағы дүкенге келесіздер ме?", "regions_onsite_aktau_1201", "актау казахский"),
    ("нужна установка кассы в актау на месте", "regions_onsite_aktau_1201", "актау на месте"),
    ("можно ли вызвать мастера в актау?", "regions_onsite_aktau_1201", "актау мастер"),

    # regions_onsite_cities_1202
    ("в каких городах вы выезжаете на место?", "regions_onsite_cities_1202", "какие города"),
    ("где есть выездное подключение?", "regions_onsite_cities_1202", "где выезд"),
    ("список городов с выездом", "regions_onsite_cities_1202", "список городов"),
    ("выездное обучение в каких городах?", "regions_onsite_cities_1202", "выездное обучение"),
    ("қай қалаларда шығасыздар?", "regions_onsite_cities_1202", "қалалар казахский"),

    # regions_onsite_karaganda_1203
    ("караганда обучение на месте есть?", "regions_onsite_karaganda_1203", "караганда обучение"),
    ("выезд в караганду возможен?", "regions_onsite_karaganda_1203", "караганда выезд"),
    ("қарағандаға шығасыздар ма?", "regions_onsite_karaganda_1203", "караганда казахский"),
    ("карагандинская область подключение офлайн", "regions_onsite_karaganda_1203", "караганд область"),
    ("в караганде есть ваш специалист?", "regions_onsite_karaganda_1203", "караганда спец"),

    # regions_onsite_pavlodar_1204
    ("павлодар установка кассы вживую", "regions_onsite_pavlodar_1204", "павлодар установка"),
    ("приедет ли мастер в павлодар?", "regions_onsite_pavlodar_1204", "павлодар мастер"),
    ("павлодарская область выезд техника", "regions_onsite_pavlodar_1204", "павлодар область"),
    ("павлодарға келесіздер ме?", "regions_onsite_pavlodar_1204", "павлодар казахский"),
    ("можно настройку в павлодаре?", "regions_onsite_pavlodar_1204", "павлодар настройка"),

    # regions_onsite_ustkam_kz_1205
    ("өскеменде оқытасыздар ма?", "regions_onsite_ustkam_kz_1205", "өскемен оқыту"),
    ("усть-каменогорск оқытуға келе аласыздар ма?", "regions_onsite_ustkam_kz_1205", "усть-камен оқыту"),
    ("шығыс қазақстанға шығасыздар ма?", "regions_onsite_ustkam_kz_1205", "ШҚО"),
    ("өскеменге маман келе ме?", "regions_onsite_ustkam_kz_1205", "өскемен маман"),
    ("вко обучение на месте есть?", "regions_onsite_ustkam_kz_1205", "ВКО рус"),

    # regions_onsite_kokshetau_kz_1206
    ("көкшетауда орнату бар ма?", "regions_onsite_kokshetau_kz_1206", "көкшетау орнату"),
    ("көкшетауға маман шығады ма?", "regions_onsite_kokshetau_kz_1206", "көкшетау маман"),
    ("ақмола облысында оқыту бар ма?", "regions_onsite_kokshetau_kz_1206", "ақмола"),
    ("кокшетау обучение на месте", "regions_onsite_kokshetau_kz_1206", "кокшетау рус"),
    ("көкшетауда выезд бар ма?", "regions_onsite_kokshetau_kz_1206", "көкшетау выезд"),

    # regions_onsite_atyrau_kz_1207
    ("атырауда қосуға болады ма?", "regions_onsite_atyrau_kz_1207", "атырау қосу"),
    ("атырау облысына шығасыздар ма?", "regions_onsite_atyrau_kz_1207", "атырау облысы"),
    ("атырауға орнатуға келесіздер ме?", "regions_onsite_atyrau_kz_1207", "атырау орнату"),
    ("атырау выезд бар ма?", "regions_onsite_atyrau_kz_1207", "атырау выезд"),
    ("атырауда специалист бар ма?", "regions_onsite_atyrau_kz_1207", "атырау спец"),

    # regions_onsite_kostanay_kz_1208
    ("қостанайда оқыту өтеді ме?", "regions_onsite_kostanay_kz_1208", "қостанай оқыту"),
    ("қостанай облысына келесіздер ме?", "regions_onsite_kostanay_kz_1208", "қостанай облысы"),
    ("қостанайға маман шығады ма?", "regions_onsite_kostanay_kz_1208", "қостанай маман"),
    ("костанай обучение очное есть?", "regions_onsite_kostanay_kz_1208", "костанай рус"),
    ("қостанайда выезд жоқ па?", "regions_onsite_kostanay_kz_1208", "қостанай выезд"),

    # regions_onsite_aktau_kz_1209
    ("актауға шебер шығады ма?", "regions_onsite_aktau_kz_1209", "актау шебер"),
    ("маңғыстау облысына келесіздер ме?", "regions_onsite_aktau_kz_1209", "маңғыстау"),
    ("актауға шығасыздар ма?", "regions_onsite_aktau_kz_1209", "актауға шығу"),
    ("актауда маман бар ма?", "regions_onsite_aktau_kz_1209", "актау маман"),
    ("актау облысы оқыту бар ма?", "regions_onsite_aktau_kz_1209", "актау оқыту"),

    # regions_onsite_list_1210
    ("қай қалаларға шығып орнатасыздар?", "regions_onsite_list_1210", "қалаларға шығу"),
    ("приехать и сразу всё настроить можно?", "regions_onsite_list_1210", "приехать настроить"),
    ("куда выезжаете на установку?", "regions_onsite_list_1210", "куда выезд"),
    ("в какие города приезжаете?", "regions_onsite_list_1210", "какие города приезд"),
    ("где можно настроить на месте?", "regions_onsite_list_1210", "на месте настроить"),

    # regions_onsite_taldykorgan_1211
    ("талдыкорган обучение кассиров", "regions_onsite_taldykorgan_1211", "талдыкорган обучение"),
    ("талдыкорганға шығасыздар ма?", "regions_onsite_taldykorgan_1211", "талдыкорган каз"),
    ("жетісу облысына выезд бар ма?", "regions_onsite_taldykorgan_1211", "жетісу"),
    ("талдыкорган выезд специалиста", "regions_onsite_taldykorgan_1211", "талдыкорган выезд"),
    ("алматинская область талдыкорган установка", "regions_onsite_taldykorgan_1211", "алмат обл"),

    # =========================================================================
    # PRICING 1212-1231 (20 секций × 5 запросов = 100 запросов)
    # =========================================================================

    # pricing_wipon_cost_1212
    ("випон сколько стоит?", "pricing_wipon_cost_1212", "випон цена"),
    ("wipon какая цена?", "pricing_wipon_cost_1212", "wipon цена"),
    ("сколько стоит ваша программа wipon?", "pricing_wipon_cost_1212", "программа wipon"),
    ("wipon почём?", "pricing_wipon_cost_1212", "почём"),
    ("цена на wipon какая?", "pricing_wipon_cost_1212", "цена wipon"),

    # pricing_wipon_pro_ukm_1213
    ("wipon pro укм сколько стоит?", "pricing_wipon_pro_ukm_1213", "pro укм цена"),
    ("модуль wipon pro активация", "pricing_wipon_pro_ukm_1213", "активация"),
    ("wipon pro для фискального оборудования", "pricing_wipon_pro_ukm_1213", "фискальное"),
    ("меня интересует wipon pro модуль", "pricing_wipon_pro_ukm_1213", "интересует"),
    ("хочу подключить wipon pro укм", "pricing_wipon_pro_ukm_1213", "подключить"),

    # pricing_wipon_program_1214
    ("интересует программа учёта wipon", "pricing_wipon_program_1214", "программа учёта"),
    ("wipon программа какие тарифы?", "pricing_wipon_program_1214", "программа тарифы"),
    ("хочу программу wipon стоимость?", "pricing_wipon_program_1214", "стоимость"),
    ("программа учёта wipon цена", "pricing_wipon_program_1214", "цена"),
    ("wipon учёт тарифы какие есть?", "pricing_wipon_program_1214", "учёт тарифы"),

    # pricing_wipon_equipment_1215
    ("какое оборудование wipon есть?", "pricing_wipon_equipment_1215", "оборудование"),
    ("wipon pos моноблоки какие?", "pricing_wipon_equipment_1215", "pos"),
    ("интересует оборудование wipon", "pricing_wipon_equipment_1215", "интересует"),
    ("wipon сканеры принтеры весы", "pricing_wipon_equipment_1215", "сканеры"),
    ("ассортимент оборудования wipon", "pricing_wipon_equipment_1215", "ассортимент"),

    # pricing_tariffs_overview_1216
    ("какие тарифы есть у вас?", "pricing_tariffs_overview_1216", "какие тарифы"),
    ("расскажите про тарифы wipon", "pricing_tariffs_overview_1216", "расскажите"),
    ("доступные тарифы программы", "pricing_tariffs_overview_1216", "доступные"),
    ("список тарифов wipon", "pricing_tariffs_overview_1216", "список"),
    ("тарифы wipon какие бывают?", "pricing_tariffs_overview_1216", "бывают"),

    # pricing_tariffs_cost_1217
    ("сколько стоят ваши тарифы?", "pricing_tariffs_cost_1217", "стоят тарифы"),
    ("цена тарифов wipon", "pricing_tariffs_cost_1217", "цена тарифов"),
    ("стоимость тарифов какая?", "pricing_tariffs_cost_1217", "стоимость тарифов"),
    ("тарифы почём у вас?", "pricing_tariffs_cost_1217", "почём тарифы"),
    ("тарифы сколько стоят?", "pricing_tariffs_cost_1217", "сколько тарифы"),

    # pricing_packages_1218
    ("есть разные пакеты программы?", "pricing_packages_1218", "пакеты"),
    ("варианты тарифов wipon", "pricing_packages_1218", "варианты"),
    ("какие пакеты можно выбрать?", "pricing_packages_1218", "какие пакеты"),
    ("пакеты wipon какие?", "pricing_packages_1218", "пакеты wipon"),
    ("есть у вас пакеты?", "pricing_packages_1218", "есть пакеты"),

    # pricing_lite_detailed_1219
    ("расскажите подробнее про lite тариф", "pricing_lite_detailed_1219", "подробнее lite"),
    ("что входит в тариф lite?", "pricing_lite_detailed_1219", "что входит lite"),
    ("lite тариф детали", "pricing_lite_detailed_1219", "детали"),
    ("тариф lite подробнее", "pricing_lite_detailed_1219", "подробнее"),
    ("lite что включает?", "pricing_lite_detailed_1219", "включает"),

    # pricing_standard_detailed_1220
    ("чем отличается standard тариф?", "pricing_standard_detailed_1220", "отличается standard"),
    ("standard тариф что даёт?", "pricing_standard_detailed_1220", "даёт standard"),
    ("тариф стандарт особенности", "pricing_standard_detailed_1220", "особенности"),
    ("standard подробнее расскажите", "pricing_standard_detailed_1220", "подробнее standard"),
    ("что в стандарте есть?", "pricing_standard_detailed_1220", "что в стандарте"),

    # pricing_pro_advantages_1221
    ("в чём преимущество pro тарифа?", "pricing_pro_advantages_1221", "преимущество pro"),
    ("pro тариф чем лучше?", "pricing_pro_advantages_1221", "чем лучше"),
    ("зачем нужен тариф pro?", "pricing_pro_advantages_1221", "зачем pro"),
    ("почему выбрать pro?", "pricing_pro_advantages_1221", "почему pro"),
    ("pro тариф преимущества", "pricing_pro_advantages_1221", "преимущества"),

    # pricing_cheapest_1222
    ("самый простой тариф какой?", "pricing_cheapest_1222", "простой"),
    ("самый недорогой тариф", "pricing_cheapest_1222", "недорогой"),
    ("дешёвый тариф есть?", "pricing_cheapest_1222", "дешёвый"),
    ("минимальный тариф цена?", "pricing_cheapest_1222", "минимальный"),
    ("тариф подешевле какой?", "pricing_cheapest_1222", "подешевле"),

    # pricing_lite_vs_standard_1223
    ("lite и standard чем отличаются?", "pricing_lite_vs_standard_1223", "lite standard отличие"),
    ("разница между lite и standard", "pricing_lite_vs_standard_1223", "разница"),
    ("сравнить lite и standard", "pricing_lite_vs_standard_1223", "сравнить"),
    ("lite или standard выбрать?", "pricing_lite_vs_standard_1223", "выбрать"),
    ("в чём разница lite standard?", "pricing_lite_vs_standard_1223", "в чём разница"),

    # pricing_upgrade_mini_standard_1224
    ("можно начать с mini потом standard?", "pricing_upgrade_mini_standard_1224", "mini потом"),
    ("повысить тариф с мини", "pricing_upgrade_mini_standard_1224", "повысить"),
    ("перейти с mini на standard", "pricing_upgrade_mini_standard_1224", "перейти"),
    ("сменить тариф с mini", "pricing_upgrade_mini_standard_1224", "сменить"),
    ("начну с мини потом обновлю", "pricing_upgrade_mini_standard_1224", "начну обновлю"),

    # pricing_pro_full_1225
    ("сколько стоит pro и что входит?", "pricing_pro_full_1225", "pro стоит входит"),
    ("pro тариф стоимость и функции", "pricing_pro_full_1225", "стоимость функции"),
    ("что в pro входит?", "pricing_pro_full_1225", "что в pro"),
    ("pro полный комплект", "pricing_pro_full_1225", "полный комплект"),
    ("всё про тариф pro расскажите", "pricing_pro_full_1225", "всё про pro"),

    # pricing_grocery_recommend_1226
    ("какой тариф для продуктового?", "pricing_grocery_recommend_1226", "продуктовый"),
    ("продуктовый магазин какой тариф?", "pricing_grocery_recommend_1226", "магазин тариф"),
    ("тариф для продуктовой розницы", "pricing_grocery_recommend_1226", "розница"),
    ("лучший тариф для продуктового", "pricing_grocery_recommend_1226", "лучший"),
    ("для продуктов что посоветуете?", "pricing_grocery_recommend_1226", "посоветуете"),

    # pricing_tariffs_kz_1227
    ("wipon тарифтерінің бағасы қанша?", "pricing_tariffs_kz_1227", "тарифтер бағасы"),
    ("тарифтердің бағасы қандай?", "pricing_tariffs_kz_1227", "тарифтердің"),
    ("қанша тұрады тариф?", "pricing_tariffs_kz_1227", "қанша тұрады"),
    ("тариф бағасы қазақша", "pricing_tariffs_kz_1227", "қазақша"),
    ("wipon тарифтері қандай?", "pricing_tariffs_kz_1227", "wipon тарифтері"),

    # pricing_chain_stores_1228
    ("тариф для сети магазинов", "pricing_chain_stores_1228", "сеть"),
    ("несколько магазинов какой тариф?", "pricing_chain_stores_1228", "несколько"),
    ("сеть точек какой тариф лучше?", "pricing_chain_stores_1228", "точек"),
    ("для сетки магазинов тариф", "pricing_chain_stores_1228", "сетка"),
    ("тариф для нескольких магазинов", "pricing_chain_stores_1228", "для нескольких"),

    # pricing_no_free_1229
    ("есть бесплатный тариф?", "pricing_no_free_1229", "бесплатный"),
    ("можно бесплатно пользоваться?", "pricing_no_free_1229", "бесплатно"),
    ("wipon бесплатно есть?", "pricing_no_free_1229", "wipon бесплатно"),
    ("есть ли бесплатный вариант?", "pricing_no_free_1229", "бесплатный вариант"),
    ("тариф бесплатно можно?", "pricing_no_free_1229", "тариф бесплатно"),

    # pricing_training_included_1230
    ("обучение входит в тариф?", "pricing_training_included_1230", "обучение входит"),
    ("есть ли обучение в тарифе?", "pricing_training_included_1230", "есть обучение"),
    ("бесплатное обучение с тарифом?", "pricing_training_included_1230", "бесплатное"),
    ("тариф с обучением?", "pricing_training_included_1230", "с обучением"),
    ("входит ли обучение?", "pricing_training_included_1230", "входит ли"),

    # pricing_lite_vs_pro_1231
    ("сравните lite и pro тарифы", "pricing_lite_vs_pro_1231", "сравните"),
    ("lite или pro что лучше?", "pricing_lite_vs_pro_1231", "что лучше"),
    ("разница lite и pro", "pricing_lite_vs_pro_1231", "разница"),
    ("lite pro сравнение", "pricing_lite_vs_pro_1231", "сравнение"),
    ("чем отличается lite от pro?", "pricing_lite_vs_pro_1231", "отличается"),

    # =========================================================================
    # PRICING 1267-1291 (25 секций × 5 запросов = 125 запросов)
    # =========================================================================

    # pricing_small_shop_tariff_1267
    ("какой тариф для небольшого магазина?", "pricing_small_shop_tariff_1267", "небольшой магазин"),
    ("маленький магазин какой тариф выбрать?", "pricing_small_shop_tariff_1267", "маленький"),
    ("тариф для мини магазина", "pricing_small_shop_tariff_1267", "мини магазин"),
    ("для маленькой точки какой тариф?", "pricing_small_shop_tariff_1267", "маленькая точка"),
    ("небольшая торговая точка тариф", "pricing_small_shop_tariff_1267", "торговая точка"),

    # pricing_trial_1268
    ("можно попробовать бесплатно?", "pricing_trial_1268", "попробовать бесплатно"),
    ("есть пробный период у вас?", "pricing_trial_1268", "пробный период"),
    ("демо доступ дадите?", "pricing_trial_1268", "демо доступ"),
    ("тестовый доступ есть?", "pricing_trial_1268", "тестовый"),
    ("бесплатный тест wipon", "pricing_trial_1268", "бесплатный тест"),

    # pricing_monthly_payment_1269
    ("можно платить помесячно?", "pricing_monthly_payment_1269", "помесячно"),
    ("ежемесячный платёж есть?", "pricing_monthly_payment_1269", "ежемесячный"),
    ("оплата в месяц возможна?", "pricing_monthly_payment_1269", "в месяц"),
    ("рассрочка помесячная?", "pricing_monthly_payment_1269", "рассрочка"),
    ("платить каждый месяц можно?", "pricing_monthly_payment_1269", "каждый месяц"),

    # pricing_annual_discount_1270
    ("скидка на годовую подписку есть?", "pricing_annual_discount_1270", "скидка годовая"),
    ("годовая подписка выгоднее?", "pricing_annual_discount_1270", "выгоднее"),
    ("экономия за год какая?", "pricing_annual_discount_1270", "экономия"),
    ("выгода годовой оплаты", "pricing_annual_discount_1270", "выгода"),
    ("скидка за год есть?", "pricing_annual_discount_1270", "за год"),

    # pricing_pharmacy_tariff_1271
    ("какой тариф для аптеки?", "pricing_pharmacy_tariff_1271", "аптека"),
    ("аптечный тариф wipon", "pricing_pharmacy_tariff_1271", "аптечный"),
    ("программа для аптеки тариф", "pricing_pharmacy_tariff_1271", "программа"),
    ("аптека какой тариф выбрать?", "pricing_pharmacy_tariff_1271", "выбрать"),
    ("wipon аптека цена", "pricing_pharmacy_tariff_1271", "цена"),

    # pricing_kassa_only_1272
    ("можно купить только кассу без программы?", "pricing_kassa_only_1272", "только касса"),
    ("касса отдельно есть?", "pricing_kassa_only_1272", "отдельно"),
    ("касса бесплатная?", "pricing_kassa_only_1272", "бесплатная"),
    ("только касса wipon", "pricing_kassa_only_1272", "только"),
    ("без программы кассу купить", "pricing_kassa_only_1272", "без программы"),

    # pricing_equipment_separate_1273
    ("оборудование входит в тариф?", "pricing_equipment_separate_1273", "входит"),
    ("оборудование отдельно покупать?", "pricing_equipment_separate_1273", "отдельно"),
    ("тариф без оборудования?", "pricing_equipment_separate_1273", "без"),
    ("нужно ли покупать оборудование?", "pricing_equipment_separate_1273", "нужно ли"),
    ("оборудование включено?", "pricing_equipment_separate_1273", "включено"),

    # pricing_minimum_kit_1274
    ("минимальный комплект для старта", "pricing_minimum_kit_1274", "минимальный"),
    ("с чего начать оборудование?", "pricing_minimum_kit_1274", "с чего"),
    ("базовый комплект цена", "pricing_minimum_kit_1274", "базовый"),
    ("комплект стандарт сколько стоит?", "pricing_minimum_kit_1274", "стандарт"),
    ("168000 комплект это что?", "pricing_minimum_kit_1274", "168000"),

    # pricing_installment_program_1275
    ("рассрочка на программу есть?", "pricing_installment_program_1275", "рассрочка программа"),
    ("программа в рассрочку", "pricing_installment_program_1275", "в рассрочку"),
    ("платить частями за программу", "pricing_installment_program_1275", "частями"),
    ("тис рассрочка есть?", "pricing_installment_program_1275", "тис"),
    ("рассрочка тариф возможна?", "pricing_installment_program_1275", "тариф"),

    # pricing_renew_1276
    ("как продлить подписку?", "pricing_renew_1276", "продлить"),
    ("продление wipon", "pricing_renew_1276", "продление"),
    ("подписка истекает что делать?", "pricing_renew_1276", "истекает"),
    ("как продлить тариф?", "pricing_renew_1276", "тариф"),
    ("продлить программу как?", "pricing_renew_1276", "программу"),

    # pricing_refund_1277
    ("можно вернуть деньги если не подошло?", "pricing_refund_1277", "вернуть"),
    ("возврат если не понравилось", "pricing_refund_1277", "возврат"),
    ("не подошла программа возврат", "pricing_refund_1277", "не подошла"),
    ("отмена подписки возврат", "pricing_refund_1277", "отмена"),
    ("возврат средств wipon", "pricing_refund_1277", "средств"),

    # pricing_wholesale_tariff_1278
    ("тариф для оптовой торговли", "pricing_wholesale_tariff_1278", "оптовая"),
    ("опт какой тариф выбрать?", "pricing_wholesale_tariff_1278", "опт"),
    ("оптовые цены тариф поддерживает?", "pricing_wholesale_tariff_1278", "оптовые цены"),
    ("программа для опта тариф", "pricing_wholesale_tariff_1278", "для опта"),
    ("оптовая торговля wipon", "pricing_wholesale_tariff_1278", "торговля"),

    # pricing_updates_included_1279
    ("обновления входят в тариф?", "pricing_updates_included_1279", "обновления"),
    ("обновления бесплатно?", "pricing_updates_included_1279", "бесплатно"),
    ("платить за обновления надо?", "pricing_updates_included_1279", "платить"),
    ("апдейты в тарифе есть?", "pricing_updates_included_1279", "апдейты"),
    ("обновления программы бесплатные?", "pricing_updates_included_1279", "программы"),

    # pricing_corporate_1280
    ("есть корпоративные скидки?", "pricing_corporate_1280", "корпоративные"),
    ("скидки для сетей магазинов", "pricing_corporate_1280", "для сетей"),
    ("индивидуальные условия есть?", "pricing_corporate_1280", "индивидуальные"),
    ("большая сеть скидка есть?", "pricing_corporate_1280", "большая сеть"),
    ("корпоративный тариф", "pricing_corporate_1280", "корпоративный"),

    # pricing_freeze_1281
    ("можно заморозить подписку?", "pricing_freeze_1281", "заморозить"),
    ("пауза подписки возможна?", "pricing_freeze_1281", "пауза"),
    ("приостановить тариф", "pricing_freeze_1281", "приостановить"),
    ("остановить подписку на время", "pricing_freeze_1281", "остановить"),
    ("заморозка wipon", "pricing_freeze_1281", "заморозка"),

    # pricing_cafe_tariff_1282
    ("тариф для кафе какой?", "pricing_cafe_tariff_1282", "кафе"),
    ("для кафешки какой тариф?", "pricing_cafe_tariff_1282", "кафешка"),
    ("программа для кафе цена", "pricing_cafe_tariff_1282", "программа кафе"),
    ("кафе wipon тариф", "pricing_cafe_tariff_1282", "wipon кафе"),
    ("небольшое кафе тариф выбрать", "pricing_cafe_tariff_1282", "небольшое"),

    # pricing_support_included_1283
    ("техподдержка входит в тариф?", "pricing_support_included_1283", "техподдержка"),
    ("поддержка включена?", "pricing_support_included_1283", "включена"),
    ("бесплатная техподдержка?", "pricing_support_included_1283", "бесплатная"),
    ("тариф с поддержкой?", "pricing_support_included_1283", "с поддержкой"),
    ("входит ли поддержка в цену?", "pricing_support_included_1283", "входит"),

    # pricing_online_shop_1284
    ("тариф для интернет-магазина", "pricing_online_shop_1284", "интернет-магазин"),
    ("онлайн магазин wipon тариф", "pricing_online_shop_1284", "онлайн"),
    ("маркетплейсы тариф какой?", "pricing_online_shop_1284", "маркетплейсы"),
    ("e-commerce тариф wipon", "pricing_online_shop_1284", "e-commerce"),
    ("для интернет магазина что выбрать?", "pricing_online_shop_1284", "что выбрать"),

    # pricing_family_1285
    ("есть семейный тариф?", "pricing_family_1285", "семейный"),
    ("тариф для семьи", "pricing_family_1285", "для семьи"),
    ("домашний тариф wipon", "pricing_family_1285", "домашний"),
    ("для дома wipon подойдёт?", "pricing_family_1285", "для дома"),
    ("личное использование wipon", "pricing_family_1285", "личное"),

    # pricing_addon_modules_1286
    ("можно докупить опции к тарифу?", "pricing_addon_modules_1286", "докупить"),
    ("добавить модули к тарифу", "pricing_addon_modules_1286", "добавить"),
    ("расширить тариф можно?", "pricing_addon_modules_1286", "расширить"),
    ("дополнительные модули", "pricing_addon_modules_1286", "дополнительные"),
    ("опции к тарифу есть?", "pricing_addon_modules_1286", "опции"),

    # pricing_beauty_salon_1287
    ("тариф для салона красоты", "pricing_beauty_salon_1287", "салон красоты"),
    ("парикмахерская тариф wipon", "pricing_beauty_salon_1287", "парикмахерская"),
    ("бьюти тариф какой?", "pricing_beauty_salon_1287", "бьюти"),
    ("косметолог тариф wipon", "pricing_beauty_salon_1287", "косметолог"),
    ("салон красоты wipon цена", "pricing_beauty_salon_1287", "цена"),

    # pricing_employee_training_1288
    ("обучение сотрудников входит?", "pricing_employee_training_1288", "сотрудников"),
    ("обучение кассиров в тарифе?", "pricing_employee_training_1288", "кассиров"),
    ("обучение персонала включено?", "pricing_employee_training_1288", "персонала"),
    ("бесплатное обучение есть?", "pricing_employee_training_1288", "бесплатное"),
    ("входит ли обучение работников?", "pricing_employee_training_1288", "работников"),

    # pricing_construction_tariff_1289
    ("тариф для строительного магазина", "pricing_construction_tariff_1289", "строительный"),
    ("строймаг тариф какой выбрать?", "pricing_construction_tariff_1289", "строймаг"),
    ("стройматериалы тариф wipon", "pricing_construction_tariff_1289", "стройматериалы"),
    ("программа для стройки цена", "pricing_construction_tariff_1289", "для стройки"),
    ("строительный магазин wipon", "pricing_construction_tariff_1289", "wipon"),

    # pricing_franchise_1290
    ("тариф для франшизы какой?", "pricing_franchise_1290", "франшиза"),
    ("франчайзинг тариф wipon", "pricing_franchise_1290", "франчайзинг"),
    ("сетевая структура тариф", "pricing_franchise_1290", "сетевая"),
    ("несколько франчайзи тариф", "pricing_franchise_1290", "франчайзи"),
    ("франшиза wipon какой тариф?", "pricing_franchise_1290", "wipon"),

    # pricing_devices_unlimited_1291
    ("сколько устройств можно подключить?", "pricing_devices_unlimited_1291", "устройств"),
    ("ограничение по устройствам есть?", "pricing_devices_unlimited_1291", "ограничение"),
    ("количество касс не ограничено?", "pricing_devices_unlimited_1291", "касс"),
    ("сколько касс можно подключить?", "pricing_devices_unlimited_1291", "сколько касс"),
    ("лимит устройств какой?", "pricing_devices_unlimited_1291", "лимит"),

    # =========================================================================
    # TIS 1232-1251 (20 секций × 5 запросов = 100 запросов)
    # =========================================================================

    # tis_pricing_1232
    ("сколько стоит тис wipon?", "tis_pricing_1232", "стоит тис"),
    ("тис цена какая?", "tis_pricing_1232", "цена"),
    ("тис тарифы wipon", "tis_pricing_1232", "тарифы"),
    ("стоимость тис wipon", "tis_pricing_1232", "стоимость"),
    ("тис рассрочка цена?", "tis_pricing_1232", "рассрочка"),

    # tis_includes_1233
    ("что входит в тис wipon?", "tis_includes_1233", "что входит"),
    ("тис функционал какой?", "tis_includes_1233", "функционал"),
    ("тис возможности какие?", "tis_includes_1233", "возможности"),
    ("что включает тис?", "tis_includes_1233", "включает"),
    ("тис состав что там?", "tis_includes_1233", "состав"),

    # tis_taxes_1234
    ("какие налоги сдавать через тис?", "tis_taxes_1234", "налоги"),
    ("тис налоговая отчётность", "tis_taxes_1234", "отчётность"),
    ("форма 910 через тис?", "tis_taxes_1234", "910"),
    ("тис сдача отчётов", "tis_taxes_1234", "сдача"),
    ("отчётность в тис есть?", "tis_taxes_1234", "в тис"),

    # tis_benefits_ip_1235
    ("что даёт подключение к тис?", "tis_benefits_ip_1235", "даёт"),
    ("тис выгода для ип", "tis_benefits_ip_1235", "выгода"),
    ("преимущества тис для предпринимателя", "tis_benefits_ip_1235", "преимущества"),
    ("зачем тис для ип?", "tis_benefits_ip_1235", "зачем"),
    ("тис лимиты для ип какие?", "tis_benefits_ip_1235", "лимиты"),

    # tis_nds_limit_1236
    ("тис увеличивает лимит ндс?", "tis_nds_limit_1236", "увеличивает"),
    ("лимит ндс с тис какой?", "tis_nds_limit_1236", "какой"),
    ("ндс повышение с тис", "tis_nds_limit_1236", "повышение"),
    ("567 миллионов ндс тис", "tis_nds_limit_1236", "567"),
    ("ндс с тис сколько можно?", "tis_nds_limit_1236", "сколько"),

    # tis_usn_limit_1237
    ("какой порог по упрощёнке с тис?", "tis_usn_limit_1237", "порог"),
    ("лимит упрощёнка тис", "tis_usn_limit_1237", "лимит"),
    ("369 миллионов упрощёнка тис", "tis_usn_limit_1237", "369"),
    ("максимальный доход с тис", "tis_usn_limit_1237", "максимальный"),
    ("упрощёнка порог тис какой?", "tis_usn_limit_1237", "какой"),

    # tis_stay_ip_1238
    ("можно оставаться ип с большим оборотом?", "tis_stay_ip_1238", "оставаться ип"),
    ("тис при большом обороте", "tis_stay_ip_1238", "большой оборот"),
    ("не переходить на тоо с тис?", "tis_stay_ip_1238", "не переходить"),
    ("остаться ип с тис", "tis_stay_ip_1238", "остаться"),
    ("высокая выручка ип тис", "tis_stay_ip_1238", "высокая выручка"),

    # tis_functions_1239
    ("что входит в функционал тис?", "tis_functions_1239", "функционал"),
    ("тис модули какие?", "tis_functions_1239", "модули"),
    ("полный функционал тис", "tis_functions_1239", "полный"),
    ("тис что умеет?", "tis_functions_1239", "умеет"),
    ("перечень функций тис", "tis_functions_1239", "перечень"),

    # tis_advantages_1240
    ("какие преимущества тис wipon?", "tis_advantages_1240", "преимущества"),
    ("плюсы тис какие?", "tis_advantages_1240", "плюсы"),
    ("чем хорош тис?", "tis_advantages_1240", "чем хорош"),
    ("выгоды тис wipon", "tis_advantages_1240", "выгоды"),
    ("зачем нужен тис?", "tis_advantages_1240", "зачем"),

    # tis_online_kassa_1241
    ("тис работает с онлайн кассой?", "tis_online_kassa_1241", "онлайн касса"),
    ("есть касса в тис?", "tis_online_kassa_1241", "есть касса"),
    ("тис фискализация чеков", "tis_online_kassa_1241", "фискализация"),
    ("чеки офд через тис?", "tis_online_kassa_1241", "офд"),
    ("касса в тис включена?", "tis_online_kassa_1241", "включена"),

    # tis_bank_integration_1242
    ("тис интегрируется с банками?", "tis_bank_integration_1242", "банками"),
    ("pos терминалы в тис", "tis_bank_integration_1242", "pos"),
    ("эквайринг тис поддерживает?", "tis_bank_integration_1242", "эквайринг"),
    ("безнал в тис", "tis_bank_integration_1242", "безнал"),
    ("оплата картой тис", "tis_bank_integration_1242", "картой"),

    # tis_quick_setup_1243
    ("долго настраивать тис?", "tis_quick_setup_1243", "долго"),
    ("тис быстро подключить?", "tis_quick_setup_1243", "быстро"),
    ("сложно настроить тис?", "tis_quick_setup_1243", "сложно"),
    ("тис установка сколько времени?", "tis_quick_setup_1243", "сколько"),
    ("быстрый запуск тис", "tis_quick_setup_1243", "запуск"),

    # tis_form_910_auto_1244
    ("тис автоматизирует форму 910?", "tis_form_910_auto_1244", "автоматизирует"),
    ("форма 910 автоматически тис", "tis_form_910_auto_1244", "автоматически"),
    ("910 автомат через тис", "tis_form_910_auto_1244", "автомат"),
    ("тис сдача 910 сама?", "tis_form_910_auto_1244", "сдача"),
    ("автозаполнение 910 тис", "tis_form_910_auto_1244", "автозаполнение"),

    # tis_installment_1245
    ("сколько стоит рассрочка на тис?", "tis_installment_1245", "рассрочка"),
    ("тис в рассрочку можно?", "tis_installment_1245", "можно"),
    ("помесячно тис оплата", "tis_installment_1245", "помесячно"),
    ("22084 тис это рассрочка?", "tis_installment_1245", "22084"),
    ("265000 тис рассрочка?", "tis_installment_1245", "265000"),

    # tis_tax_reduction_1246
    ("тис помогает снизить налоги?", "tis_tax_reduction_1246", "снизить"),
    ("уменьшение налогов с тис", "tis_tax_reduction_1246", "уменьшение"),
    ("экономия на налогах тис", "tis_tax_reduction_1246", "экономия"),
    ("налоговая оптимизация тис", "tis_tax_reduction_1246", "оптимизация"),
    ("меньше налогов с тис?", "tis_tax_reduction_1246", "меньше"),

    # tis_hr_1247
    ("кадровый учёт в тис есть?", "tis_hr_1247", "кадровый"),
    ("тис зарплата считает?", "tis_hr_1247", "зарплата"),
    ("сотрудники в тис", "tis_hr_1247", "сотрудники"),
    ("учёт персонала тис", "tis_hr_1247", "персонала"),
    ("тис кадры есть?", "tis_hr_1247", "кадры"),

    # tis_official_year_1248
    ("с какого года тис официально?", "tis_official_year_1248", "какого года"),
    ("когда тис признали?", "tis_official_year_1248", "признали"),
    ("тис в реестре когда?", "tis_official_year_1248", "реестре"),
    ("2021 тис официальный?", "tis_official_year_1248", "2021"),
    ("тис официальный статус когда?", "tis_official_year_1248", "статус"),

    # tis_marking_1249
    ("тис работает с маркировкой?", "tis_marking_1249", "маркировка"),
    ("маркированные товары в тис", "tis_marking_1249", "маркированные"),
    ("прослеживаемость тис есть?", "tis_marking_1249", "прослеживаемость"),
    ("тис учёт маркировки", "tis_marking_1249", "учёт"),
    ("маркировка поддерживается тис?", "tis_marking_1249", "поддерживается"),

    # tis_vs_regular_program_1250
    ("чем тис отличается от обычной программы?", "tis_vs_regular_program_1250", "отличается"),
    ("тис vs обычный учёт", "tis_vs_regular_program_1250", "vs"),
    ("зачем тис если есть программа?", "tis_vs_regular_program_1250", "если есть"),
    ("разница тис и программы", "tis_vs_regular_program_1250", "разница"),
    ("тис лучше обычного учёта?", "tis_vs_regular_program_1250", "лучше"),

    # tis_target_audience_1251
    ("кому подходит тис wipon?", "tis_target_audience_1251", "подходит"),
    ("тис для кого нужен?", "tis_target_audience_1251", "для кого"),
    ("кому нужен тис?", "tis_target_audience_1251", "нужен"),
    ("тис для каких предпринимателей?", "tis_target_audience_1251", "предпринимателей"),
    ("целевая аудитория тис", "tis_target_audience_1251", "аудитория"),

    # =========================================================================
    # PRODUCTS 1252-1266 (15 секций × 5 запросов = 75 запросов)
    # =========================================================================

    # products_wipon_retail_what_1252
    ("что такое wipon розница?", "products_wipon_retail_what_1252", "что такое"),
    ("wipon розница это что?", "products_wipon_retail_what_1252", "это что"),
    ("розница wipon расскажите", "products_wipon_retail_what_1252", "расскажите"),
    ("программа wipon розница", "products_wipon_retail_what_1252", "программа"),
    ("wipon retail что это?", "products_wipon_retail_what_1252", "retail"),

    # products_wipon_retail_audience_1253
    ("для кого подходит wipon розница?", "products_wipon_retail_audience_1253", "для кого"),
    ("кому нужна wipon розница?", "products_wipon_retail_audience_1253", "кому"),
    ("wipon розница для каких магазинов?", "products_wipon_retail_audience_1253", "для каких"),
    ("розница для каких бизнесов?", "products_wipon_retail_audience_1253", "бизнесов"),
    ("wipon розница целевая аудитория", "products_wipon_retail_audience_1253", "аудитория"),

    # products_wipon_retail_functions_1254
    ("что входит в wipon розница?", "products_wipon_retail_functions_1254", "что входит"),
    ("функционал wipon розница", "products_wipon_retail_functions_1254", "функционал"),
    ("wipon розница что умеет?", "products_wipon_retail_functions_1254", "что умеет"),
    ("возможности wipon розница", "products_wipon_retail_functions_1254", "возможности"),
    ("модули wipon розница", "products_wipon_retail_functions_1254", "модули"),

    # products_wipon_retail_kassa_1255
    ("есть касса в wipon розница?", "products_wipon_retail_kassa_1255", "касса"),
    ("фискализация в рознице wipon", "products_wipon_retail_kassa_1255", "фискализация"),
    ("касса встроенная розница", "products_wipon_retail_kassa_1255", "встроенная"),
    ("чеки офд розница wipon", "products_wipon_retail_kassa_1255", "чеки"),
    ("wipon розница онлайн касса", "products_wipon_retail_kassa_1255", "онлайн"),

    # products_wipon_retail_scales_1256
    ("wipon розница с весами работает?", "products_wipon_retail_scales_1256", "весами"),
    ("весовой товар в рознице", "products_wipon_retail_scales_1256", "весовой"),
    ("подключить весы к рознице", "products_wipon_retail_scales_1256", "подключить"),
    ("продажа на вес wipon розница", "products_wipon_retail_scales_1256", "на вес"),
    ("весы розница wipon", "products_wipon_retail_scales_1256", "весы"),

    # products_wipon_retail_marketplaces_1257
    ("wipon розница маркетплейсы поддерживает?", "products_wipon_retail_marketplaces_1257", "маркетплейсы"),
    ("kaspi интеграция розница", "products_wipon_retail_marketplaces_1257", "kaspi"),
    ("halyk розница интеграция", "products_wipon_retail_marketplaces_1257", "halyk"),
    ("маркетплейсы wipon подключить", "products_wipon_retail_marketplaces_1257", "подключить"),
    ("kaspi магазин розница", "products_wipon_retail_marketplaces_1257", "магазин"),

    # products_wipon_retail_marking_1258
    ("wipon розница маркировка есть?", "products_wipon_retail_marking_1258", "маркировка"),
    ("учёт маркированных товаров розница", "products_wipon_retail_marking_1258", "учёт"),
    ("маркировка поддержка розница", "products_wipon_retail_marking_1258", "поддержка"),
    ("прослеживаемость розница wipon", "products_wipon_retail_marking_1258", "прослеживаемость"),
    ("маркировка wipon работает?", "products_wipon_retail_marking_1258", "работает"),

    # products_wipon_retail_price_1259
    ("сколько стоит wipon розница?", "products_wipon_retail_price_1259", "стоит"),
    ("wipon розница цена", "products_wipon_retail_price_1259", "цена"),
    ("тарифы wipon розница", "products_wipon_retail_price_1259", "тарифы"),
    ("стоимость розница wipon", "products_wipon_retail_price_1259", "стоимость"),
    ("розница тарифы какие?", "products_wipon_retail_price_1259", "какие"),

    # products_wipon_retail_multistore_1260
    ("wipon розница несколько магазинов?", "products_wipon_retail_multistore_1260", "несколько"),
    ("мультискладской учёт розница", "products_wipon_retail_multistore_1260", "мультискладской"),
    ("сеть магазинов розница wipon", "products_wipon_retail_multistore_1260", "сеть"),
    ("подключить несколько точек розница", "products_wipon_retail_multistore_1260", "точек"),
    ("розница несколько складов", "products_wipon_retail_multistore_1260", "складов"),

    # products_wipon_retail_mobile_1261
    ("мобильное приложение wipon розница", "products_wipon_retail_mobile_1261", "мобильное"),
    ("розница на телефоне", "products_wipon_retail_mobile_1261", "телефоне"),
    ("ios android розница wipon", "products_wipon_retail_mobile_1261", "ios"),
    ("wipon розница мобильное есть?", "products_wipon_retail_mobile_1261", "есть"),
    ("розница приложение скачать", "products_wipon_retail_mobile_1261", "скачать"),

    # products_wipon_retail_purchases_1262
    ("закупки wipon розница", "products_wipon_retail_purchases_1262", "закупки"),
    ("приёмка товаров розница", "products_wipon_retail_purchases_1262", "приёмка"),
    ("перемещения розница wipon", "products_wipon_retail_purchases_1262", "перемещения"),
    ("поступления розница учёт", "products_wipon_retail_purchases_1262", "поступления"),
    ("учёт закупок розница", "products_wipon_retail_purchases_1262", "учёт"),

    # products_wipon_retail_reports_1263
    ("отчёты wipon розница какие?", "products_wipon_retail_reports_1263", "отчёты"),
    ("аналитика розница wipon", "products_wipon_retail_reports_1263", "аналитика"),
    ("abc анализ розница", "products_wipon_retail_reports_1263", "abc"),
    ("отчёт по кассирам розница", "products_wipon_retail_reports_1263", "кассирам"),
    ("какие отчёты в рознице?", "products_wipon_retail_reports_1263", "какие"),

    # products_wipon_retail_discounts_1264
    ("скидки wipon розница", "products_wipon_retail_discounts_1264", "скидки"),
    ("акции розница wipon", "products_wipon_retail_discounts_1264", "акции"),
    ("программа лояльности розница", "products_wipon_retail_discounts_1264", "лояльности"),
    ("бонусы розница wipon", "products_wipon_retail_discounts_1264", "бонусы"),
    ("скидки и акции wipon есть?", "products_wipon_retail_discounts_1264", "есть"),

    # products_wipon_retail_chain_1265
    ("wipon розница для сети магазинов", "products_wipon_retail_chain_1265", "сети"),
    ("централизованное управление розница", "products_wipon_retail_chain_1265", "централизованное"),
    ("сеть точек розница wipon", "products_wipon_retail_chain_1265", "точек"),
    ("единые цены сеть розница", "products_wipon_retail_chain_1265", "единые"),
    ("аналитика по всем точкам розница", "products_wipon_retail_chain_1265", "по всем"),

    # products_wipon_retail_difference_1266
    ("чем wipon розница отличается?", "products_wipon_retail_difference_1266", "отличается"),
    ("wipon розница vs другие программы", "products_wipon_retail_difference_1266", "vs"),
    ("преимущества wipon розница", "products_wipon_retail_difference_1266", "преимущества"),
    ("розница отличие от других", "products_wipon_retail_difference_1266", "отличие"),
    ("почему wipon розница лучше?", "products_wipon_retail_difference_1266", "лучше"),

    # =========================================================================
    # EQUIPMENT 1292-1300 (9 секций × 5 запросов = 45 запросов)
    # =========================================================================

    # equipment_kit_standard_1292
    ("что входит в комплект standard?", "equipment_kit_standard_1292", "что входит"),
    ("кассовый комплект стандарт состав", "equipment_kit_standard_1292", "состав"),
    ("pos i3 сканер принтер комплект", "equipment_kit_standard_1292", "pos i3"),
    ("комплект за 168000 что там?", "equipment_kit_standard_1292", "168000"),
    ("комплект standard wipon", "equipment_kit_standard_1292", "wipon"),

    # equipment_kit_standard_plus_1293
    ("комплект standard+ что входит?", "equipment_kit_standard_plus_1293", "standard+"),
    ("pos duo сканер принтер", "equipment_kit_standard_plus_1293", "pos duo"),
    ("комплект 248000 состав", "equipment_kit_standard_plus_1293", "248000"),
    ("стандарт плюс комплект", "equipment_kit_standard_plus_1293", "плюс"),
    ("кассовый комплект standard+", "equipment_kit_standard_plus_1293", "кассовый"),

    # equipment_kit_cheaper_1294
    ("какой комплект дешевле?", "equipment_kit_cheaper_1294", "дешевле"),
    ("самый дешёвый комплект оборудования", "equipment_kit_cheaper_1294", "самый дешёвый"),
    ("бюджетный комплект wipon", "equipment_kit_cheaper_1294", "бюджетный"),
    ("минимальная цена комплект", "equipment_kit_cheaper_1294", "минимальная"),
    ("комплект подешевле есть?", "equipment_kit_cheaper_1294", "подешевле"),

    # equipment_kit_chain_1295
    ("какой комплект для сети магазинов?", "equipment_kit_chain_1295", "сети"),
    ("оборудование для нескольких магазинов", "equipment_kit_chain_1295", "нескольких"),
    ("pos duo для сети", "equipment_kit_chain_1295", "для сети"),
    ("лучший комплект для сетки", "equipment_kit_chain_1295", "лучший"),
    ("сеть магазинов оборудование", "equipment_kit_chain_1295", "магазинов"),

    # equipment_kit_custom_1296
    ("можно собрать комплект самому?", "equipment_kit_custom_1296", "самому"),
    ("выбрать компоненты отдельно", "equipment_kit_custom_1296", "компоненты"),
    ("индивидуальный комплект оборудования", "equipment_kit_custom_1296", "индивидуальный"),
    ("кастомный комплект wipon", "equipment_kit_custom_1296", "кастомный"),
    ("свой набор оборудования собрать", "equipment_kit_custom_1296", "набор"),

    # equipment_kit_setup_included_1297
    ("настройка входит в стоимость комплекта?", "equipment_kit_setup_included_1297", "настройка"),
    ("обучение входит в комплект?", "equipment_kit_setup_included_1297", "обучение"),
    ("установка включена в цену?", "equipment_kit_setup_included_1297", "установка"),
    ("настройка и обучение в комплекте", "equipment_kit_setup_included_1297", "в комплекте"),
    ("комплект с настройкой?", "equipment_kit_setup_included_1297", "с настройкой"),

    # equipment_kit_warranty_1298
    ("гарантия на комплекты какая?", "equipment_kit_warranty_1298", "гарантия"),
    ("сколько месяцев гарантия оборудование?", "equipment_kit_warranty_1298", "месяцев"),
    ("гарантийный срок комплекта", "equipment_kit_warranty_1298", "срок"),
    ("12 месяцев гарантия wipon?", "equipment_kit_warranty_1298", "12"),
    ("гарантия wipon оборудование", "equipment_kit_warranty_1298", "wipon"),

    # equipment_kit_installment_1299
    ("комплект в рассрочку можно?", "equipment_kit_installment_1299", "рассрочку"),
    ("рассрочка на оборудование есть?", "equipment_kit_installment_1299", "оборудование"),
    ("оборудование частями оплатить", "equipment_kit_installment_1299", "частями"),
    ("купить комплект в рассрочку", "equipment_kit_installment_1299", "купить"),
    ("рассрочка на комплект wipon", "equipment_kit_installment_1299", "комплект"),

    # equipment_kit_grocery_1300
    ("комплект для продуктового магазина", "equipment_kit_grocery_1300", "продуктового"),
    ("продуктовый магазин оборудование", "equipment_kit_grocery_1300", "магазин"),
    ("какой комплект для продуктов?", "equipment_kit_grocery_1300", "продуктов"),
    ("оборудование для продуктовой точки", "equipment_kit_grocery_1300", "точки"),
    ("продукты комплект wipon какой?", "equipment_kit_grocery_1300", "какой"),
]


@dataclass
class TestResult:
    query: str
    expected_topic: str
    description: str
    found_topic: str
    is_correct: bool
    score: float
    stage: str


def run_tests() -> List[TestResult]:
    print("Инициализация retriever...")
    reset_retriever()
    retriever = CascadeRetriever(use_embeddings=False)

    print(f"Загружено секций: {len(retriever.kb.sections)}")
    print(f"Всего тестов: {len(TEST_QUERIES)}")
    print("=" * 100)

    results: List[TestResult] = []
    start_total = time.perf_counter()

    for i, (query, expected_topic, description) in enumerate(TEST_QUERIES, 1):
        search_results = retriever.search(query, top_k=1)

        if search_results:
            found_topic = search_results[0].section.topic
            score = search_results[0].score
            stage = search_results[0].stage.value
        else:
            found_topic = "NOT_FOUND"
            score = 0.0
            stage = "none"

        is_correct = found_topic == expected_topic
        results.append(TestResult(query, expected_topic, description, found_topic, is_correct, score, stage))

        status = "OK" if is_correct else "FAIL"
        print(f"[{i:3d}/{len(TEST_QUERIES)}] [{status}] {query[:45]:<45} -> {found_topic[:35]:<35} ({score:.2f})")

    print(f"\nОбщее время: {time.perf_counter() - start_total:.1f}s")
    return results


def print_summary(results: List[TestResult]):
    print("\n" + "=" * 100)
    print("ИТОГИ")
    print("=" * 100)

    correct = sum(1 for r in results if r.is_correct)
    total = len(results)
    accuracy = correct / total * 100

    print(f"\nОбщая точность: {correct}/{total} ({accuracy:.1f}%)")

    # По категориям (по prefix topic)
    categories: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r.expected_topic.split("_")[0]
        if cat not in categories:
            categories[cat] = {"correct": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.is_correct:
            categories[cat]["correct"] += 1

    print("\nТочность по категориям:")
    print("-" * 60)
    for cat, stats in sorted(categories.items(), key=lambda x: -x[1]["total"]):
        cat_accuracy = stats["correct"] / stats["total"] * 100
        bar = "█" * int(cat_accuracy / 10) + "░" * (10 - int(cat_accuracy / 10))
        status = "OK" if cat_accuracy >= 80 else "LOW"
        print(f"  {cat:12s}: {stats['correct']:3d}/{stats['total']:3d} ({cat_accuracy:5.1f}%) {bar} [{status}]")

    # По стадиям поиска
    stages: Dict[str, int] = {}
    for r in results:
        stages[r.stage] = stages.get(r.stage, 0) + 1

    print("\nРаспределение по стадиям поиска:")
    for stage, count in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"  {stage}: {count} ({count/total*100:.1f}%)")

    # Ошибки
    failures = [r for r in results if not r.is_correct]
    if failures:
        print(f"\n{'=' * 100}")
        print(f"ОШИБКИ ({len(failures)}):")
        print("-" * 100)
        for i, r in enumerate(failures[:30], 1):
            print(f"{i:2d}. {r.query[:50]}")
            print(f"    Ожидал: {r.expected_topic}")
            print(f"    Получил: {r.found_topic} (score={r.score:.2f}, stage={r.stage})")
        if len(failures) > 30:
            print(f"    ... и ещё {len(failures) - 30} ошибок")


def main():
    print("=" * 100)
    print("ТЕСТ ТОЧНОСТИ НОВЫХ СЕКЦИЙ 1200-1300")
    print("=" * 100)

    results = run_tests()
    print_summary(results)

    accuracy = sum(1 for r in results if r.is_correct) / len(results) * 100
    print(f"\nРезультат: {'PASSED' if accuracy >= 85 else 'FAILED'} ({accuracy:.1f}%)")

    return 0 if accuracy >= 85 else 1


if __name__ == "__main__":
    sys.exit(main())
