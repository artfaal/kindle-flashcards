#!/usr/bin/env python3
"""
Kindle → noji.io: Генератор карточек через OpenAI API
Извлекает слова из vocab.db и создает качественные карточки
"""

import sqlite3
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError as e:
    missing_lib = str(e).split("'")[1] if "'" in str(e) else "неизвестная библиотека"
    print(f"❌ Ошибка: библиотека {missing_lib} не установлена")
    print("\nУстановите зависимости командой:")
    print("   pip install openai python-dotenv")
    sys.exit(1)

# Загружаем переменные окружения с переопределением системных
load_dotenv(override=True)

# ============================================================================
# ГЛАВНЫЙ ПРОМПТ ДЛЯ ГЕНЕРАЦИИ КАРТОЧЕК
# ============================================================================
SYSTEM_PROMPT = """You are generating flashcards for a Russian speaker learning English.

OUTPUT FORMAT (front % back):
<h3><b>word</b> <small>/pronunciation/</small></h3><p><i>"Original sentence with _____ blank."</i></p>%🇷🇺 <b>перевод / другой вариант перевода / ещё вариант перевода</b><br>🇬🇧 <i>short definition</i><br>📝 part of speech • <b>level</b> • ⭐ importance/10<br>🔗 common collocation<br>✅ synonym<br>❌ antonym<br>📖 <i>"Simple sentence example."</i><br>💡 <i>мнемоническая ассоциация на русском</i>

RULES:
- Front: word + pronunciation + EXACT original sentence with word replaced by _____
- Back: all info in single lines, no lists or complex formatting
- Translation: context-appropriate Russian translation first, then add 2-3 alternative meanings separated by / if they exist
- Definition: B1 level English, max 15 words, never use the word itself
- Original context: use EXACT original sentence provided, no length limit
- Grammar: part of speech • CEFR level • importance 1-10
- Collocations: ONE most common phrase with the word
- Synonyms/Antonyms: separate lines, one each
- Example: NEW simple sentence (not the original one)
- Memory tip: Russian mnemonic association
- Use only short HTML tags: b, i, small, br
- Double newline between cards
- Importance scale: * 9-10 = top 500 words (be, have, go, make, think, get, see) * 7-8 = top 3000 words (often, explain, create, remember) * 5-6 = common everyday words (coax, borough, persuade) * 3-4 = specialized but known (glower, stencil, squirm) * 1-2 = rare, technical, archaic

OUTPUT ONLY THE CARDS."""
# ============================================================================


class KindleCardsGenerator:
    def __init__(self):
        self.state_file = '.kindle_vocab_state.json'
        self.output_dir = 'kindle_cards_output'
        self.vocab_db_paths = [
            './vocab.db',
            '/Volumes/Kindle/system/vocabulary/vocab.db',  # Mac
            'E:\\system\\vocabulary\\vocab.db',  # Windows
            'D:\\system\\vocabulary\\vocab.db',
            'F:\\system\\vocabulary\\vocab.db',
            '/mnt/kindle/system/vocabulary/vocab.db'  # Linux
        ]

        # Инициализация OpenAI клиента
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("❌ API ключ OpenAI не найден!")
            print("\nПолучите ключ на: https://platform.openai.com/api-keys")
            print("Затем добавьте в .env файл:")
            print("\n   OPENAI_API_KEY='sk-proj-ВАШ_КЛЮЧ'")
            sys.exit(1)

        self.client = OpenAI(api_key=api_key)

        # Настройки модели из .env
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.3'))
        self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '3000'))
        self.batch_size = int(os.getenv('BATCH_SIZE', '40'))
        self.test_limit = int(os.getenv('TEST_LIMIT', '5'))
        self.stats = {
            'api_calls': 0,
            'total_tokens': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0
        }


    def print_header(self):
        """Печатает заголовок"""
        print("=" * 70)
        print("📚 Kindle → noji.io: Генерация карточек (OpenAI)")
        print("=" * 70)
        print()

    def find_vocab_db(self):
        """Ищет vocab.db"""
        print("🔍 Поиск vocab.db...")

        for path in self.vocab_db_paths:
            if os.path.exists(path):
                print(f"✓ Найден: {path}")
                return path

        print("❌ vocab.db не найден!")
        print("\nПроверьте следующие места:")
        for path in self.vocab_db_paths:
            print(f"  • {path}")
        print("\nИли скопируйте vocab.db в текущую папку")
        return None

    def load_state(self):
        """Загружает state"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass

        return {
            'last_processed_timestamp': 0,
            'processed_words': []
        }

    def save_state(self, state):
        """Сохраняет state"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def clean_word(self, word):
        """Очищает слово от пунктуации"""
        cleaned = re.sub(r'^[^\w\s-]+|[^\w\s-]+$', '', word)
        return cleaned.lower().strip()

    def extract_words(self, db_path, last_timestamp):
        """Извлекает новые слова из vocab.db"""
        print("📖 Извлечение слов...")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
        SELECT DISTINCT
            w.word,
            w.stem,
            l.usage,
            b.title,
            l.timestamp
        FROM WORDS w
        JOIN LOOKUPS l ON w.id = l.word_key
        LEFT JOIN BOOK_INFO b ON l.book_key = b.id
        WHERE w.lang = 'en'
          AND l.timestamp > ?
        ORDER BY l.timestamp ASC
        """

        cursor.execute(query, (last_timestamp,))
        results = cursor.fetchall()
        conn.close()

        words_data = []
        books = set()

        for word, stem, usage, title, timestamp in results:
            words_data.append({
                'word': word,
                'stem': stem or word,
                'usage': usage or '',
                'book': title or 'Unknown',
                'timestamp': timestamp
            })
            if title:
                books.add(title)

        print(f"✨ Найдено {len(words_data)} новых записей из {len(books)} книг")

        if books:
            print(f"📖 Книги: {', '.join(list(books)[:3])}")
            if len(books) > 3:
                print(f"          ... и ещё {len(books) - 3}")

        return words_data

    def filter_words(self, words_data, processed_words):
        """Фильтрует слова"""
        filtered = []
        seen = set()

        for item in words_data:
            word = self.clean_word(item['word'])

            # Пропускаем пустые, длинные фразы, дубликаты
            if not word or len(word.split()) > 5 or word in processed_words or word in seen:
                continue

            seen.add(word)
            item['clean_word'] = word
            filtered.append(item)

        return filtered

    def generate_cards_batch(self, words_batch):
        """Генерирует карточки для батча через OpenAI API"""
        # Формируем список слов с оригинальными контекстами
        words_list = []
        for item in words_batch:
            word = item['clean_word']
            original_context = item.get('usage', '').strip()

            if original_context:
                words_list.append(f"- {word}\n  Original context: \"{original_context}\"")
            else:
                words_list.append(f"- {word}")

        words_text = "\n\n".join(words_list)
        user_prompt = f"Generate flashcards for these words with their original contexts:\n\n{words_text}"

        try:
            # Используем правильный параметр для новых моделей
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            }

            # Для gpt-5 используем max_completion_tokens и убираем temperature
            if self.model.startswith('gpt-5'):
                api_params["max_completion_tokens"] = self.max_tokens
                # temperature не поддерживается для gpt-5
            else:
                api_params["max_tokens"] = self.max_tokens
                api_params["temperature"] = self.temperature

            response = self.client.chat.completions.create(**api_params)

            # Статистика токенов
            self.stats['api_calls'] += 1
            self.stats['prompt_tokens'] += response.usage.prompt_tokens
            self.stats['completion_tokens'] += response.usage.completion_tokens
            self.stats['total_tokens'] += response.usage.total_tokens

            cards_text = response.choices[0].message.content.strip()

            return cards_text

        except Exception as e:
            print(f"❌ Ошибка API: {e}")
            return None

    def run(self, test_mode=False):
        """Основная функция"""
        if test_mode:
            print("🧪 ТЕСТОВЫЙ РЕЖИМ")
            print("=" * 70)

        self.print_header()

        # Поиск базы данных
        db_path = self.find_vocab_db()
        if not db_path:
            return

        print()

        # Загрузка state
        state = self.load_state()

        # Извлечение слов
        words_data = self.extract_words(db_path, state['last_processed_timestamp'])

        if not words_data:
            print("✅ Нет новых слов для обработки")
            return

        # Фильтрация
        filtered_words = self.filter_words(words_data, state['processed_words'])

        if not filtered_words:
            print("✅ Все новые слова уже обработаны")
            return

        # Ограничение для тестового режима
        if test_mode:
            filtered_words = filtered_words[:self.test_limit]
            print(f"🧪 Тестовый режим: ограничение до {self.test_limit} слов")

        print()
        print(f"🎴 Генерация карточек для {len(filtered_words)} слов...")
        print()

        # Разбиваем на батчи
        batches = [filtered_words[i:i + self.batch_size]
                   for i in range(0, len(filtered_words), self.batch_size)]

        all_cards = []
        processed_words = []
        max_timestamp = state['last_processed_timestamp']

        # Обрабатываем каждый батч
        for i, batch in enumerate(batches, 1):
            print(f"   Батч {i}/{len(batches)} ({len(batch)} слов)... ", end='', flush=True)

            cards_text = self.generate_cards_batch(batch)

            if cards_text:
                all_cards.append(cards_text)

                # Обновляем обработанные слова
                for item in batch:
                    processed_words.append(item['clean_word'])
                    max_timestamp = max(max_timestamp, item['timestamp'])

                print(f"✓ ({self.stats['total_tokens']:,} токенов)")
            else:
                print("✗ Ошибка")
                break

        if not all_cards:
            print("\n❌ Не удалось сгенерировать карточки")
            return

        print()
        print("💾 Сохранение...")

        # Создаём папку
        os.makedirs(self.output_dir, exist_ok=True)

        # Генерируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"noji_cards_{timestamp}.txt"
        filepath = os.path.join(self.output_dir, filename)

        # Сохраняем карточки
        with open(filepath, 'w', encoding='utf-8') as f:
            content = "\n\n".join(all_cards)
            f.write(content)

        print(f"✓ Создан файл: {filename}")

        # Обновляем state (только если не тестовый режим)
        if not test_mode:
            state['last_processed_timestamp'] = max_timestamp
            state['processed_words'].extend(processed_words)
            state['processed_words'] = list(set(state['processed_words']))  # Удаляем дубликаты
            self.save_state(state)
        else:
            print("🧪 Тестовый режим: состояние не сохранено")

        # Считаем стоимость (GPT-4o-mini)
        # Input: $0.15 / 1M tokens
        # Output: $0.60 / 1M tokens
        input_cost = (self.stats['prompt_tokens'] / 1_000_000) * 0.15
        output_cost = (self.stats['completion_tokens'] / 1_000_000) * 0.60
        total_cost = input_cost + output_cost

        # Статистика
        print()
        print("📊 Статистика:")
        print(f"   • Обработано слов: {len(processed_words)}")
        print(f"   • Сгенерировано карточек: {len(processed_words)}")
        print(f"   • API вызовов: {self.stats['api_calls']}")
        print(f"   • Использовано токенов: {self.stats['total_tokens']:,}")
        print(f"     - Input: {self.stats['prompt_tokens']:,}")
        print(f"     - Output: {self.stats['completion_tokens']:,}")
        print(f"   • Стоимость: ~${total_cost:.4f}")
        print(f"   • Всего в базе: {len(state['processed_words']):,} уникальных слов")
        print()
        print(f"✅ ГОТОВО! Импортируйте {filename} в noji.io")
        print("=" * 70)


if __name__ == '__main__':
    import sys

    generator = KindleCardsGenerator()

    # Проверяем аргумент test
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        generator.run(test_mode=True)
    else:
        generator.run()
