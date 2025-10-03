# Kindle → noji.io: Генератор карточек

Приложение для автоматической генерации карточек из базы данных Kindle Vocabulary Builder для импорта в [noji.io](https://noji.io).

## Функционал

- 📚 **Извлекает слова** из базы данных Kindle Vocabulary Builder (vocab.db)
- 🤖 **Генерирует качественные карточки** через OpenAI API (GPT-4o-mini)
- 🔄 **Инкрементальная обработка** - обрабатывает только новые слова
- 📊 **Подробная статистика** - токены, стоимость API вызовов, прогресс
- 🎯 **Оптимизированные промпты** для изучения английского русскоязычными
- 💾 **Готовый формат** для импорта в noji.io

## Формат карточек

Карточки создаются в формате **Front/Back** для оптимального изучения:

### **Front (лицевая сторона):**
- **Слово** с произношением
- **Контекст** из книги с пропуском
- **Вопрос** для активного вспоминания

### **Back (обратная сторона):**
- **Перевод** на русский (1-3 основных значения)
- **Определение** на английском (уровень B1)
- **Грамматика** - часть речи, уровень CEFR, важность
- **Коллокации** - 2-3 устойчивых сочетания
- **Синонимы/Антонимы** с выделением
- **Пример** предложения
- **Мнемоника** для запоминания

## Установка и запуск

### 1. Клонирование и настройка

```bash
git clone <repository-url>
cd kindle-flashcards
```

### 2. Создание виртуального окружения

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация (Linux/Mac)
source venv/bin/activate

# Активация (Windows)
venv\\Scripts\\activate
```

### 3. Установка зависимостей

```bash
pip install openai python-dotenv
```

### 4. Настройка API ключа

Получите API ключ на [platform.openai.com/api-keys](https://platform.openai.com/api-keys) и создайте файл `.env`:

```env
# OpenAI API Configuration
OPENAI_API_KEY="sk-proj-ВАШ_КЛЮЧ"
OPENAI_MODEL="gpt-4o-mini"
OPENAI_TEMPERATURE=0.3
OPENAI_MAX_TOKENS=3000

# Processing Configuration
BATCH_SIZE=40
```

### 5. Подготовка базы данных Kindle

Скопируйте файл `vocab.db` из вашего Kindle:

**Стандартные пути:**
- **Mac:** `/Volumes/Kindle/system/vocabulary/vocab.db`
- **Windows:** `E:\system\vocabulary\vocab.db` (может быть D:, F:)
- **Linux:** `/mnt/kindle/system/vocabulary/vocab.db`

Или просто скопируйте файл в папку проекта как `vocab.db`.

### 6. Запуск

```bash
python generate_cards.py
```

## Настройки в .env

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `OPENAI_API_KEY` | API ключ OpenAI | обязательно |
| `OPENAI_MODEL` | Модель для генерации | `gpt-5` |
| `OPENAI_TEMPERATURE` | Температура (0-1) | `0.3` |
| `OPENAI_MAX_TOKENS` | Максимум токенов | `3000` |
| `BATCH_SIZE` | Размер батча слов | `40` |

## Доступные модели OpenAI

- `gpt-5`
- `gpt-5-mini`
- `gpt-5-nano`
- `gpt-4.1`
- `gpt-4.1-mini`
- `gpt-4.1-nano`

## Как это работает

1. **Поиск базы** - приложение ищет `vocab.db` в стандартных местах
2. **Инкрементальная обработка** - обрабатывает только новые слова с последнего запуска
3. **Батчевая генерация** - отправляет слова группами в OpenAI API
4. **Сохранение результата** - создает файл в папке `kindle_cards_output/`
5. **Обновление состояния** - запоминает обработанные слова в `.kindle_vocab_state.json`

## Структура выходных файлов

```
kindle_cards_output/
└── noji_cards_20241003_142530.txt
```

Файлы готовы для импорта в noji.io в формате Front/Back (разделение через TAB):

```html
<h3><strong>coax</strong> <small>/kəʊks/</small></h3><p><em>"She _____ him into joining us."</em></p>%<h4>🇷🇺 Перевод:</h4><p>уговаривать; заманивать</p><h4>🇬🇧 Definition:</h4><p><em>To gently persuade someone to do something</em></p><h4>📝 Grammar:</h4><p>verb • <strong>B2</strong> • ⭐ 6/10</p><h4>🔗 Collocations:</h4><ul><li>coax into doing</li><li>coax out of</li><li>coax a smile</li></ul><h4>↔️ Syn/Ant:</h4><p>Syn: persuade, cajole<br>Ant: <s>deter</s></p><h4>📖 Example:</h4><p><em>"She coaxed him into joining us."</em></p><h4>💡 Memory tip:</h4><p><em>COAks ≈ уКОАксивает (звуковое сходство)</em></p>
```

## Стоимость использования

Приложение использует модель GPT-4o-mini:
- **Входящие токены:** $0.15 за 1M токенов
- **Исходящие токены:** $0.60 за 1M токенов

**Примерная стоимость:** ~$0.01-0.05 за 100 карточек

## Состояние и возобновление

Приложение сохраняет прогресс в файле `.kindle_vocab_state.json`:
- Отметка времени последней обработки
- Список уже обработанных слов
- При следующем запуске обрабатывает только новые слова

## Проблемы и решения

### API ключ не найден
Убедитесь, что файл `.env` существует и содержит корректный `OPENAI_API_KEY`.

### vocab.db не найден
Проверьте подключение Kindle или скопируйте файл вручную в папку проекта.

### Ошибки API
- Проверьте баланс на аккаунте OpenAI
- Убедитесь в корректности API ключа
- При превышении лимитов уменьшите `BATCH_SIZE`

## Требования

- Python 3.7+
- Библиотеки: `openai`, `python-dotenv`
- Действующий API ключ OpenAI
- База данных Kindle Vocabulary Builder (vocab.db)