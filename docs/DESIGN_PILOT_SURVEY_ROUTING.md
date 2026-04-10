# Design Document: Pilot Survey Routing

## 1. Контекст

`pilot_survey` должен вести клиента по списку из 8 вопросов: один вопрос за раз, с пониманием что клиент по смыслу ответил на текущий вопрос, и переходом к следующему вопросу.

При этом клиент в любой момент может спросить о компании, продукте, цене или условиях. Такой вопрос не должен ломать место в опросе: бот отвечает через существующие KB/factual/pricing routes и возвращается к текущему вопросу опроса.

## 2. Четыре routing-state текущего turn-а

Это не отдельные `StateMachine` states и не отдельный активный flow. Это результат маршрутизации одного входящего сообщения перед финальным `action + next_state`.

| Routing-state | Когда срабатывает | Задача | Поведение state |
|---|---|---|---|
| `survey_answer` | Клиент по смыслу нормально ответил на текущий вопрос опроса и не задал вопрос о компании | Зафиксировать что текущий вопрос закрыт и перейти к следующему вопросу | `next_state` переходит на следующий survey-state |
| `company_question` | Клиент спрашивает о компании, продукте, цене, условиях, функциях или интеграциях, но не отвечает на текущий вопрос опроса | Ответить через существующий factual/pricing route | `next_state` остаётся текущим survey-state |
| `mixed` | Клиент одновременно по смыслу ответил на текущий вопрос и задал вопрос о компании | Зафиксировать что текущий вопрос закрыт, ответить на вопрос клиента и продолжить опрос | `action` отвечает на вопрос, `next_state` переходит на следующий survey-state |
| `unclear` | Нельзя уверенно понять: это ответ на survey-вопрос или вопрос о компании | Коротко уточнить смысл сообщения | `next_state` остаётся текущим survey-state |

## 3. Место в архитектуре

Routing-state определяется внутри Blackboard pipeline отдельным source, а не отдельным flow и не генератором. Это сохраняет текущую архитектуру: `StateMachine` хранит state, `Blackboard` принимает решение, `Generator` отвечает только за текст свободного ответа.

```text
User message
  -> Classifier / intent detection
  -> Blackboard.begin_turn()
  -> Blackboard sources:
       PriceQuestionSource / FactQuestionSource
       PilotSurveyAnswerGateSource
  -> ConflictResolver: final action + next_state
  -> pilot_survey_response_plan
  -> optional Generator answer
  -> deterministic survey question suffix / final phrase
```

## 4. Как использовать существующий пайплайн

`survey_answer` опирается не на извлечение бизнес-данных, а на semantic answer gate: отдельную проверку, что сообщение клиента является достаточным ответом на текущий survey-вопрос.

`company_question` опирается на существующие `PriceQuestionSource` и `FactQuestionSource`: они выбирают `answer_with_pricing` или `answer_with_facts`, а `PilotSurveyAnswerGateSource` не предлагает переход.

`mixed` использует уже существующее свойство factual/pricing action: оно остаётся `combinable=True` и поэтому может совместиться с transition на следующий survey-state.

`unclear` должен давать уточняющий action без перехода. Его задача - не двигать опрос, пока нет надёжного ответа на текущий survey-вопрос.

## 5. Детерминированные survey-вопросы

Точные формулировки 8 вопросов должны храниться в `pilot_survey` flow как единый источник истины. Каждый survey-state знает:
- какой вопрос сейчас активен;
- какую точную фразу вопроса нужно отправить;
- какой semantic contract определяет нормальный ответ;
- в какой следующий survey-state перейти после принятого ответа.

Генератор не должен формулировать следующий survey-вопрос. Он может отвечать только на свободный вопрос клиента о компании, продукте, цене или условиях. Текущий или следующий survey-вопрос добавляется после генерации как детерминированный suffix из YAML.

Канонический YAML-ключ для движения дальше — `transitions.answer_accepted`. Не использовать параллельные ключи вроде `parameters.next_survey_state` для той же цели.

## 6. Runtime-поведение по routing-state

`survey_answer`: semantic gate принимает ответ на текущий вопрос, state переходит в следующий survey-state, бот отправляет точный вопрос из следующего state без вызова генератора. Если следующий state — `survey_complete`, применяется completion contract.

`company_question`: оставить текущий survey-state, вызвать существующий generator через `answer_with_facts` / `answer_with_pricing`, затем детерминированно добавить точный вопрос текущего state.

`mixed`: semantic gate принимает ответ на текущий вопрос, state переходит в следующий survey-state, generator отвечает на вопрос клиента о компании, затем код детерминированно добавляет точный вопрос следующего state. Если следующий state — `survey_complete`, вместо вопроса добавляется финальная фраза.

`unclear`: не принимать ответ и не двигать state. Отправить короткое уточнение без перехода; generator можно не вызывать, если уточнение покрывается детерминированной фразой.

## 7. Минимальная точка интеграции

Нужен тонкий слой планирования ответа после `Blackboard / ConflictResolver`, но до вызова генератора и финальной отправки ответа пользователю.

Условное имя: `pilot_survey_response_plan`.

Задача слоя:
- определить, нужно ли пропустить generator;
- определить, нужно ли вызвать generator для factual/pricing answer;
- определить, какой survey-вопрос добавить: текущий или следующий;
- не менять логику KB/retrieval/generator, если turn не относится к `pilot_survey`.

```text
Blackboard decision: action + next_state
  -> pilot_survey_response_plan
  -> optional Generator answer
  -> deterministic survey question suffix
  -> final response
```

`pilot_survey_response_plan` не принимает решение о переходе state. Он только собирает финальный текст ответа из уже принятого `Blackboard`-решения и deterministic survey-текста.

Планировщик читает routing-signal из `blackboard.get_context_signals()` после `process_turn()` и до следующего `Blackboard.begin_turn()`. Если в реализации удобнее передавать `sm_result`, bot-layer должен явно скопировать этот signal в context для `pilot_survey_response_plan`; сам `ResolvedDecision.to_sm_result()` сейчас не является SSOT для context signals.

Если `PilotSurveyAnswerGateSource` дал только transition без action, `ConflictResolver` может вернуть дефолтный action вроде `continue_current_goal`. Для `survey_answer` и pure completion это считается no-op для текста: `pilot_survey_response_plan` не должен из-за него вызывать generator.

## 8. Граница ответственности

`pilot_survey` flow отвечает за порядок 8 вопросов и точные формулировки.

`PilotSurveyAnswerGateSource` отвечает только за semantic decision: достаточно ли сообщение клиента отвечает на текущий survey-вопрос, чтобы перейти дальше. Он не обязан извлекать и сохранять бизнес-данные из ответа.

`PriceQuestionSource` и `FactQuestionSource` отвечают за маршрутизацию вопросов о компании в `answer_with_pricing` / `answer_with_facts`.

`Generator` отвечает только на свободную часть сообщения клиента. Он не выбирает и не перефразирует survey-вопросы.

`pilot_survey_response_plan` склеивает результат: либо отправляет только детерминированный вопрос, либо берёт ответ генератора и добавляет к нему детерминированный survey-вопрос.

## 9. Semantic answer gate вместо extractor

Для `pilot_survey` не требуется вытаскивать структурированные данные из ответа клиента. Достаточно понять, что ответ по общему смыслу валиден для текущего вопроса.

Это отдельная задача от обычного `extracted_data`:
- обычный extractor пытается извлечь поля вроде `company_size`, `contact_info`, `pain_point`;
- semantic answer gate отвечает на бинарный вопрос: "можно ли считать текущий survey-вопрос закрытым?";
- содержимое ответа клиента можно не сохранять или сохранять только в transcript/history, без превращения в business field.

Контракт валидности должен жить рядом с вопросом в `pilot_survey` flow:

```yaml
survey_q3:
  required_data: []
  transitions:
    answer_accepted: survey_q4
  parameters:
    deterministic_question: "По каким признакам вы поймёте, что пилот успешен?"
    answer_gate:
      valid_if: "Клиент назвал любой критерий, метрику, результат или ожидание от пилота."
      invalid_if: "Клиент только задал встречный вопрос, ушёл от ответа или написал бессодержательное 'не знаю'."
      min_confidence: 0.70
      clarify: "Коротко уточните, пожалуйста: по какому результату вы поймёте, что пилот прошёл успешно?"
```

`PilotSurveyAnswerGateSource` читает текущий survey-state, берёт `deterministic_question` и `answer_gate`, затем возвращает один из routing-state: `survey_answer`, `company_question`, `mixed`, `unclear`.

Если ответ принят, источник предлагает transition на следующий survey-state. Если ответ не принят, transition не предлагается.

## 10. Контракт `PilotSurveyAnswerGateSource`

Source активен только если текущий flow — `pilot_survey`, а текущий state содержит `parameters.deterministic_question` и `parameters.answer_gate`. В greeting, terminal/final state и non-`pilot_survey` flows source должен abstain.

Source должен регистрироваться после `PriceQuestionSource` / `FactQuestionSource` и до generic transition/data collectors. Практический ориентир для `priority_order`: после 15 и до 20.

Source читает:
- текущий `state`;
- `user_message`;
- primary intent и secondary intents из classifier/context envelope;
- `deterministic_question` и `answer_gate` текущего survey-state;
- transition на следующий survey-state из конфигурации текущего state.

`company_question_present` должен определяться через существующую intent taxonomy: price-related и fact-question intents. Gate не должен заводить параллельную таксономию вопросов о компании. Если нужного company/FAQ-интента не хватает, расширяется существующая taxonomy/fact-question конфигурация, а не `PilotSurveyAnswerGateSource`.

Source возвращает turn-local context signal:

```json
{
  "source": "pilot_survey_answer_gate",
  "state": "survey_q3",
  "routing_state": "survey_answer | company_question | mixed | unclear",
  "answer_accepted": true,
  "company_question_present": false,
  "confidence": 0.86,
  "reason": "short internal reason, not user-facing"
}
```

Если `confidence < answer_gate.min_confidence`, gate работает fail-closed: `answer_accepted=false`, `routing_state=unclear`, transition не предлагается. Если `min_confidence` не задан, дефолт — `0.70`.

Proposal contract:
- `survey_answer`: context signal + transition на следующий survey-state, без action proposal.
- `company_question`: context signal, без transition; action ожидается от `PriceQuestionSource` / `FactQuestionSource`.
- `mixed`: context signal + transition на следующий survey-state; action ожидается от `PriceQuestionSource` / `FactQuestionSource`.
- `unclear`: context signal, без transition и без generator-required action; `pilot_survey_response_plan` отправляет deterministic `answer_gate.clarify`.

Инвариант: если signal говорит `company_question_present=true`, но итоговый decision не содержит factual/pricing action, это не должно молча превращаться в обычный survey turn. Безопасное поведение — fail-closed: не двигать state и уточнить/логировать проблему конфигурации taxonomy.

Transition proposal mergeable by design: в текущем `ConflictResolver` `combinable` относится к action proposal, а не к transition proposal. Для `mixed` важно, чтобы factual/pricing action от `PriceQuestionSource` / `FactQuestionSource` оставался `combinable=True`. Transition от `PilotSurveyAnswerGateSource` должен иметь priority `NORMAL`, потому что hard-stop/safety/guard actions должны иметь возможность победить.

Source должен abstain или fail-closed на hard-stop intent вроде `rejection`, `farewell`, `request_human`, чтобы не продвигать опрос против явного отказа клиента.

Survey-states не должны двигаться через `required_data` / `data_complete`: для них `required_data: []`, а прогресс идёт только через `transitions.answer_accepted`, предложенный `PilotSurveyAnswerGateSource`. Это защищает дизайн от скрытого возврата к extractor-based логике.

Survey-states не должны наследовать широкие sales-progression mixins, которые могут неявно перевести state по `info_provided`, `agreement`, `demo_request` и похожим sales-интентам. Допустимы только явно выбранные safety/exit/question-handling механизмы, которые не нарушают порядок 8 вопросов.

## 11. Зафиксированные продуктовые решения

Диалог инициируем мы сами, не клиент. Поэтому greeting живёт отдельно от обычного inbound turn: сначала бот отправляет детерминированное приветствие с вопросом, удобно ли сейчас пройти короткий опрос. Runtime выставляет state в `survey_consent`, а не сразу в `survey_q1`.

Если первый ответ клиента — согласие (`agreement`), обычная intent-based маршрутизация переводит state из `survey_consent` в `survey_q1`, а `pilot_survey_response_plan` отправляет deterministic question из `survey_q1` без generator. Если первый ответ — отказ, просьба связаться позже, objection-интент или явное завершение (`rejection`, `hard_no`, `callback_request`, `objection_*`, `farewell`, `end_conversation`), state переходит в финальный `survey_declined`, и бот отправляет deterministic `final_phrase` без следующих survey-вопросов.

На старте outbound-сценария runtime должен выставить state в `survey_consent` до ожидания первого ответа клиента. Это не synthetic user turn: это стартовая отправка ботом deterministic greeting без вопроса `1/8`.

После валидного ответа на последний вопрос бот не переходит в свободный autonomous-режим. Для pure `survey_answer` он не вызывает generator и отправляет заранее заданную финальную детерминированную фразу из `pilot_survey` flow.

Если клиент задаёт вопрос о компании вместо ответа, бот отвечает и возвращает текущий survey-вопрос. При первом таком возврате можно добавить вопрос прямо. Если клиент задаёт вопросы о компании повторно на том же survey-state, `pilot_survey_response_plan` должен использовать более мягкую связку, например: "И вернусь к вопросу: {deterministic_question}".

Это не требует отдельного нового flow-режима. Достаточно учитывать в `pilot_survey_response_plan`, был ли текущий survey-вопрос уже повторён после factual/pricing answer.

SSOT для этого repeat-check — transcript/history, а не отдельное persistent поле. Планировщик ответа смотрит, был ли раньше на этом же survey-state factual/pricing ответ, к которому уже добавлялась точная `deterministic_question`. Стартовое outbound-сообщение с consent-вопросом не считается повтором.

## 12. Простая логика движения state

Логика движения уже выражена в четырёх routing-state:

`survey_answer`: получили валидный по смыслу ответ на текущий survey-вопрос, значит переходим дальше.

`company_question`: получили вопрос о компании вместо ответа, значит отвечаем и остаёмся на текущем survey-state.

`mixed`: получили и валидный ответ на survey-вопрос, и вопрос о компании, значит отвечаем на вопрос о компании и переходим дальше.

`unclear`: не получили валидный ответ и не получили понятный factual/pricing question, значит уточняем и остаёмся на текущем survey-state.

Иными словами, переход делает не extractor и не generator, а `PilotSurveyAnswerGateSource`: если текущий ответ принят, он предлагает transition на следующий survey-state; если не принят, transition не предлагает.

## 13. Completion contract

Последний survey-state ведёт не к обычному вопросу, а к terminal/completion state внутри `pilot_survey`.

Когда `PilotSurveyAnswerGateSource` принимает ответ на последний вопрос:
- предлагается transition в `survey_complete`;
- `pilot_survey_response_plan` отправляет deterministic `final_phrase` из `pilot_survey` flow.

Если последний turn был `mixed`, factual/pricing generator всё ещё вызывается для вопроса клиента, но вместо следующего survey-вопроса к ответу добавляется deterministic `final_phrase`. Если это pure `survey_answer`, generator не вызывается.

`survey_complete` считается концом сценария опроса. Дальнейшее поведение вне scope этого документа и не должно неявно переключаться в autonomous flow.

Каноническое место финальной фразы — `survey_complete.parameters.final_phrase`.

## 14. Минимальная test matrix

Перед реализацией сценарий считается покрытым, если есть тесты на:
- старт outbound: greeting с consent-вопросом, state установлен в `survey_consent`, `1/8` ещё не отправлен;
- consent accepted: `agreement` переводит `survey_consent` в `survey_q1` и отправляет `1/8` без generator;
- consent declined: `rejection`/`callback_request`/`objection_*` переводит `survey_consent` в `survey_declined` и мягко завершает без следующих вопросов;
- `survey_answer`: валидный ответ двигает на следующий question без generator;
- `company_question`: factual/pricing answer остаётся на текущем question и добавляет текущий deterministic question;
- повторный `company_question` на том же state использует мягкую связку "И вернусь к вопросу...";
- `mixed`: factual/pricing answer + переход на следующий deterministic question;
- `unclear`: deterministic clarify без перехода;
- последний валидный ответ: transition в `survey_complete` + deterministic final phrase без generator.
- `mixed` на последнем вопросе: factual/pricing answer + transition в `survey_complete` + deterministic final phrase.

## 15. Implementation anchors

Канонический flow живёт в `src/yaml_config/flows/pilot_survey/`: `flow.yaml` задаёт entrypoint `survey_consent`, greeting-переменную и phase, `states.yaml` задаёт consent-развилку, 8 точных вопросов, `answer_gate`-контракты, `transitions.answer_accepted`, `survey_complete.parameters.final_phrase` и `survey_declined.parameters.final_phrase`.

После загрузки `ConfigLoader` runtime читает resolved YAML-параметры из `state_config._resolved_params`. YAML-ключи всё равно остаются `parameters.deterministic_question`, `parameters.answer_gate` и `parameters.final_phrase`; `_resolved_params` — это только внутреннее представление после template substitution.

`PilotSurveyAnswerGateSource` зарегистрирован в `SourceRegistry` после `PriceQuestionSource` / `FactQuestionSource` и до `DataCollectorSource`, чтобы видеть уже предложенные factual/pricing action и, при валидном ответе, предложить только transition `answer_accepted`.

`pilot_survey_response_plan` живёт после Blackboard decision и перед генератором. Он не решает state transition, а только выбирает: отправить детерминированный следующий вопрос/финальную фразу без генератора или вызвать generator для ответа о компании и добавить детерминированный suffix.

`SalesBot.build_outbound_start_message()` строит стартовое outbound-сообщение из `outbound_greeting` без synthetic user turn и без записи в transcript. Первый deterministic survey-вопрос (`survey_q1.deterministic_question`) отправляется только после consent-перехода из `survey_consent` в `survey_q1`. Это важно, чтобы повтор `company_question` считался только по реальным turn-ам после factual/pricing ответа.

API/runtime entrypoint должен передавать `flow_name="pilot_survey"` в `SessionManager/SalesBot`. Для bot-initiated старта он вызывает `build_outbound_start_message()` отдельно от обычного inbound turn. В текущем API-контракте это выражается двумя входами:

- explicit start: request с `flow_name="pilot_survey"` и `start=true` без `message.text` и без attachments; такой start fail-fast отклоняется для non-`pilot_survey` flow и для уже начатой survey-сессии;
- control command: обычный inbound request с `message.text="/start_pilot"`, без attachments и без `start=true`; runtime перезапускает session в `pilot_survey`, не пишет `/start_pilot` как user turn и отвечает тем же `outbound_greeting`.

Дальнейшие обычные inbound-сообщения без явного `flow_name` должны продолжать активный flow сессии. Default `autonomous` используется только при создании новой сессии, а не как принудительный switch уже активного `pilot_survey`.
