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

# Загружаем переменные окружения
load_dotenv()

# ============================================================================
# ГЛАВНЫЙ ПРОМПТ ДЛЯ ГЕНЕРАЦИИ КАРТОЧЕК
# ============================================================================
SYSTEM_PROMPT = """You are generating flashcards for a Russian speaker learning English.

OUTPUT FORMAT (one card per line, front % back, two empty lines between cards):
<h3><strong>word</strong> <small>/pronunciation/</small></h3><p><em>"Sentence with _____ blank."</em></p>%<h4>🇷🇺 Перевод:</h4><p>перевод</p><h4>🇬🇧 Definition:</h4><p><em>short definition</em></p><h4>📝 Grammar:</h4><p>part of speech • <strong>level</strong> • ⭐ importance/10</p><h4>🔗 Collocations:</h4><ul><li>phrase1</li><li>phrase2</li><li>phrase3</li></ul><h4>↔️ Syn/Ant:</h4><p>Syn: synonyms<br>Ant: <s>antonyms</s></p><h4>📖 Example:</h4><p><em>"Full sentence example."</em></p><h4>💡 Memory tip:</h4><p><em>mnemonic association</em></p>

RULES:
- Front side: word with pronunciation, context sentence with blank (no question)
- Back side: complete information with minimal HTML formatting
- Translation: accurate Russian translation (1-3 main meanings if word is common)
- Definition: B1 level English, max 15 words, NEVER use the word itself in definition
- Context: create a simple sentence from the original usage, replace the word with _____
- POS/CEFR/IPA: part of speech • CEFR level (A1-C2) • IPA pronunciation (BrE, add AmE if different)
- Importance scale:
  * 9-10 = top 500 words (be, have, go, make, think, get, see)
  * 7-8 = top 3000 words (often, explain, create, remember)  
  * 5-6 = common everyday words (coax, borough, persuade)
  * 3-4 = specialized but known (glower, stencil, squirm)
  * 1-2 = rare, technical, archaic
- Collocations: 2-3 most common phrases/collocations with the word
- Syn/Ant: 1-2 synonyms, 1-2 antonyms
- Memory tip: create a mnemonic association with Russian sounds, words, or visual images
- Use bold only for: word, level, avoid excessive formatting
- Always add TWO empty lines between cards

OUTPUT ONLY THE CARDS. No explanations, no comments, no extra formatting."""
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
        # Формируем список слов для промпта
        words_list = "\n".join([f"- {item['clean_word']}" for item in words_batch])

        user_prompt = f"Generate flashcards for these words:\n\n{words_list}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            # Статистика токенов
            self.stats['api_calls'] += 1
            self.stats['prompt_tokens'] += response.usage.prompt_tokens
            self.stats['completion_tokens'] += response.usage.completion_tokens
            self.stats['total_tokens'] += response.usage.total_tokens

            cards_text = response.choices[0].message.content.strip()

            return cards_text

        except Exception as e:
            print(f"\n❌ Ошибка API: {e}")
            return None

    def run(self):
        """Основная функция"""
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
            content = "\n\n\n".join(all_cards)
            f.write(content)

        print(f"✓ Создан файл: {filename}")

        # Обновляем state
        state['last_processed_timestamp'] = max_timestamp
        state['processed_words'].extend(processed_words)
        state['processed_words'] = list(set(state['processed_words']))  # Удаляем дубликаты
        self.save_state(state)

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
    generator = KindleCardsGenerator()
    generator.run()
