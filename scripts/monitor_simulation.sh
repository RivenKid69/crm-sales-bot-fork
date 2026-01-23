#!/bin/bash
# =============================================================================
# Мониторинг симуляции в реальном времени
# =============================================================================

while true; do
  clear
  echo "================================================================================"
  echo "                    CRM SALES BOT - МОНИТОРИНГ СИМУЛЯЦИИ"
  echo "================================================================================"
  echo ""
  echo "⏰ Время: $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Подсчет завершенных диалогов
  completed=$(grep -c "PASS\|FAIL" simulation_output.log 2>/dev/null || echo 0)
  passed=$(grep -c "PASS" simulation_output.log 2>/dev/null || echo 0)
  failed=$(grep -c "FAIL" simulation_output.log 2>/dev/null || echo 0)
  percent=$((completed))

  echo "📊 ПРОГРЕСС:"
  echo "  • Завершено: ${completed}/100 (${percent}%)"
  echo "  • Успешно: ${passed}"
  echo "  • Провалено: ${failed}"

  if [ $completed -gt 0 ]; then
    pass_rate=$((passed * 100 / completed))
    echo "  • Pass Rate: ${pass_rate}%"
  fi

  echo ""
  echo "📈 ПОСЛЕДНИЕ 10 РЕЗУЛЬТАТОВ:"
  grep "PASS\|FAIL" simulation_output.log 2>/dev/null | tail -10 | while read line; do
    if echo "$line" | grep -q "PASS"; then
      echo "  ✅ $line"
    else
      echo "  ❌ $line"
    fi
  done

  echo ""
  echo "💻 GPU (NVIDIA RTX 5090):"
  nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu --format=csv,noheader,nounits 2>/dev/null | \
    awk -F, '{
      printf "  • Загрузка GPU: %s%%\n", $1
      printf "  • Загрузка памяти: %s%%\n", $2
      printf "  • VRAM: %sMB / %sMB (%.1f%%)\n", $3, $4, ($3/$4*100)
      printf "  • Энергопотребление: %sW\n", $5
      printf "  • Температура: %s°C\n", $6
    }' || echo "  • (недоступно)"

  echo ""
  echo "🖥️  CPU:"
  cpu_usage=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
  echo "  • Общая загрузка: ${cpu_usage}%"

  # Проверяем процесс симуляции
  if ps aux | grep -q "[r]un_detailed_simulation"; then
    python_cpu=$(ps aux | grep "[r]un_detailed_simulation" | awk '{print $3}')
    python_mem=$(ps aux | grep "[r]un_detailed_simulation" | awk '{print $4}')
    echo "  • Python процесс: ${python_cpu}% CPU, ${python_mem}% RAM"
  else
    echo "  • Python процесс: не найден"
  fi

  # Проверяем Ollama
  if ps aux | grep -q "[o]llama runner"; then
    ollama_cpu=$(ps aux | grep "[o]llama runner" | head -1 | awk '{print $3}')
    ollama_mem=$(ps aux | grep "[o]llama runner" | head -1 | awk '{print $4}')
    echo "  • Ollama runner: ${ollama_cpu}% CPU, ${ollama_mem}% RAM"
  else
    echo "  • Ollama runner: не найден"
  fi

  echo ""
  echo "⏱️  ВРЕМЯ:"

  # Вычисляем примерное оставшееся время
  if [ $completed -gt 0 ]; then
    start_time=$(stat -c %Y simulation_output.log 2>/dev/null || echo 0)
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    elapsed_min=$((elapsed / 60))
    elapsed_sec=$((elapsed % 60))

    avg_time_per_dialog=$((elapsed / completed))
    remaining=$((100 - completed))
    est_remaining=$((avg_time_per_dialog * remaining))
    est_remaining_min=$((est_remaining / 60))
    est_remaining_sec=$((est_remaining % 60))

    echo "  • Прошло: ${elapsed_min}m ${elapsed_sec}s"
    echo "  • Осталось (примерно): ${est_remaining_min}m ${est_remaining_sec}s"
    echo "  • Среднее время на диалог: ${avg_time_per_dialog}s"
  else
    echo "  • Ожидание первого завершенного диалога..."
  fi

  echo ""
  echo "================================================================================"
  echo "Обновление каждые 5 секунд. Нажмите Ctrl+C для выхода."
  echo "Полный лог: tail -f simulation_output.log"
  echo "================================================================================"

  sleep 5
done
