"""Motorun nasıl kullanıldığını gösteren kısa demo: python demo.py"""

from engine import (
    Board,
    Cell,
    forced_cells,
    from_code,
    save_json,
    to_code,
    validate_partial,
    validate_solution,
)

# 1) Değişken boyutlu tahta — boyut hiçbir yerde sabit değil.
board = Board(6, 6)
board.set_clue(1, 1, [3])
board.set_clue(1, 4, [1, 1])
board.set_clue(4, 2, [0])
print("Tahta:")
print(board.to_text())

# 2) Kısa kodla aynı bulmacayı tek satırda tanımlamak.
print("\nKısa kod:", to_code(board))
print("Kodu geri okuma:", from_code(to_code(board)).clues == board.clues)

# 3) Tek bir ipucundan çıkarılabilen zorunlu hücreler.
print("\nZorunlu hücreler (0 ipucusunun çevresi dahil):")
for pos, state in sorted(forced_cells(board).items()):
    print(f"  {pos} -> {state.name}")

# 4) Hamle ve canlı geri bildirim.
board.set_cell(3, 2, Cell.FILLED)   # 0 ipucusunun komşusu: anında çelişki
result = validate_partial(board)
print("\nKısmi doğrulama:", "temiz" if result.ok else result.issues[0].message)

board.set_cell(3, 2, Cell.UNKNOWN)
print("Geri alındı, kısmi doğrulama:", "temiz" if validate_partial(board).ok else "hata")

# 5) Bitmiş çözüm kontrolü.
print("Çözüldü mü:", validate_solution(board).ok)

# 6) Kütüphaneye kaydetme.
path = save_json(board, "puzzles/ornek.json", meta={"baslik": "Demo", "zorluk": "kolay"})
print("\nKaydedildi:", path)
