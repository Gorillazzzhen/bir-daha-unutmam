import os
import openai
import numpy as np
import redis
import argparse


class NoteFinder:
    def __init__(self, folder):
        self.folder = folder
        self.notes = self.load_notes()

    def load_notes(self):
        notes = {}
        for filename in os.listdir(self.folder):
            if filename.endswith(".md"):
                with open(os.path.join(self.folder, filename), 'r') as f:
                    notes[filename] = f.read()
        return notes

    @staticmethod
    def get_embeddings(texts):
        # Replace with your OpenAI API key
        #openai.api_key = "your_api_key"

        # Filter out empty strings
        texts = [text for text in texts if text.strip()]

        if not texts:
            return np.array([])

        response = openai.Embedding.create(model="text-embedding-ada-002", input=texts)
        embeddings = response['data']
        
        return np.array([np.array(emb["embedding"]) for emb in embeddings])

    def save_embedding_to_redis(self, embedding, filename):
        r = redis.Redis()
        key = f"embedding:{filename}"
        response = r.set(key, embedding.tobytes())
        print(f"{filename} Embedding Redise eklendi.")

    def load_embeddings_from_redis(self):
        r = redis.Redis()
        keys = r.keys("embedding:*")
        note_dates = [key.decode("utf-8").split(":")[1] for key in keys]
        embeddings = []
        for key in keys:
            embedding = np.frombuffer(r.get(key), dtype=np.float64)
            embeddings.append(embedding)
        return note_dates, np.array(embeddings)

    def update_embedding(self, filename):
        if filename in self.notes:
            content = self.notes[filename]
            embedding = self.get_embeddings([content])[0]
            self.save_embedding_to_redis(embedding, filename)
        else:
            print(f"{filename} dosyası bulunamadı.")

    def find_closest(self, query_embedding, note_embeddings):
        return note_embeddings.dot(query_embedding).argmax()

    def update_all_embeddings(self):
        for filename, content in self.notes.items():
            if content.strip():
                embedding = self.get_embeddings([content])[0]
                self.save_embedding_to_redis(embedding, filename)
            else:
                print(f"Doküman boş {filename}. Atlandı.")
    
    def chat_gpt(self, document, question):
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Sen doküman asistanısın. Dokümanı oku ve soruları cevapla. Sadece dokümanla ilgili soruları cevapla."},
                {"role": "user", "content": document},
                {"role": "assistant", "content": "Ben bir doküman asistanıyım. Yukarıdaki dokümanı okuyup ve sorularınızı cevaplayacağım. Sadece dokümanla ilgili sorularınıza cevap verebilirim, başka sorulara kesinlikle dokümanda yok diye cevap veririm."},
                {"role": "user", "content": question},
            ],
        )
        answer = response.choices[0].message['content']
        return answer

    def run(self, args):
        if args.dosya:
            if args.dosya.lower() == "hepsi":
                self.update_all_embeddings()
            else:
                self.update_embedding(args.dosya)
        else:
            note_dates, note_embeddings = self.load_embeddings_from_redis()

            while True:
                text = input("Soru: ")
                if text.lower() == "bitir":
                    break

                query_embedding = self.get_embeddings([text])[0]
                index = self.find_closest(query_embedding, note_embeddings)
                print(f"En yakın not: {note_dates[index]}")

                #print(self.notes[note_dates[index]])
                
                # Get the answer from the document using ChatGPT API
                document = self.notes[note_dates[index]]
                answer = self.chat_gpt(document, text)
                print(f"Cevap: {answer}")



# Import Gradio if it's available
try:
    import gradio as gr
    gradio_available = True
except ImportError:
    gradio_available = False

# NoteFinder class and other functions remain unchanged

def parse_arguments():
    parser = argparse.ArgumentParser(description="Notlarını bul")
    parser.add_argument("--dosya", type=str, help="Verisetine yeni bir not eklemek için dosya adını girin.", default=None)
    parser.add_argument("--gradio", action="store_true", help="Gradio arayüzünü kullanarak notlara ulaşın.")
    return parser.parse_args()

def main():
    folder = "notlar"
    note_finder = NoteFinder(folder)
    args = parse_arguments()
    
    if args.gradio and gradio_available:
        def ask_question(text):
            note_dates, note_embeddings = note_finder.load_embeddings_from_redis()
            query_embedding = note_finder.get_embeddings([text])[0]
            index = note_finder.find_closest(query_embedding, note_embeddings)
            document = note_finder.notes[note_dates[index]]
            answer = note_finder.chat_gpt(document, text)
            return f"En yakın not: {note_dates[index]}\nCevap: {answer}"

        def send_to_redis(filename):
            if filename == "hepsi":
                note_finder.update_all_embeddings()
                return "Tüm notlar Redis'e eklendi."
            else:
                note_finder.update_embedding(filename)
                return f"{filename} Redis'e eklendi."

        note_files = ["hepsi"] + sorted(list(note_finder.notes.keys()))

        with gr.Blocks() as demo:
            gr.Markdown("# Notlarını Bul")
            gr.Markdown("## Soru Sorarak Notlarınızdaki İlgili Bilgilere Ulaşın")

            question_text = gr.inputs.Textbox(lines=1, label="Soru")
            answer_text = gr.outputs.Textbox(label="Cevap")
            ask_button = gr.Button(value="Soru Sor", name="ask_question_button")
            ask_button.click(ask_question, inputs=[question_text], outputs=[answer_text])

            gr.Markdown("## Notları Redis'e Ekle")
            dropdown = gr.inputs.Dropdown(choices=note_files, label="Not Dosyaları")
            send_button = gr.Button(label="Redis'e Ekle", name="add_to_redis_button")
            send_result = gr.outputs.Textbox(label="Sonuç")
            send_button.click(send_to_redis, inputs=[dropdown], outputs=[send_result])

        demo.launch()
    else:
        if args.dosya:
            note_finder.run(args)
        else:
            print("Gradio is not installed or not enabled. Please install Gradio and use --gradio flag to enable the interface.")
            return

if __name__ == "__main__":
    main()