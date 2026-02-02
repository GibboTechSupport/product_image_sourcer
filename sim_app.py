import requests
import os

urls = [
    "https://loshusansupermarket.com/product_images/d/logo%207%20days__75492.jpg",
    "https://loshusansupermarket.com/product_images/m/531/7-Days_Soft_Croissant_Vanilla_60g__73679_thumb.jpg",
    "https://loshusansupermarket.com/product_images/y/logo%20abeer%20younis__75360.jpg",
    "https://loshusansupermarket.com/product_images/b/751/Abeers_Baklawa_Small_2228_1_tagged__56983_thumb.jpg",
    "https://loshusansupermarket.com/product_images/y/624/Abeers_Date_Maamoul_Cookie_2231_1_tagged__95397_thumb.jpg",
    "https://loshusansupermarket.com/product_images/h/266/Alessi_Breadsticks_Sesame_4.4oz__53948_thumb.jpg",
    "https://loshusansupermarket.com/product_images/b/414/Alessi_Breadsticks_Thin_3oz__70081_thumb.jpg",
    "https://loshusansupermarket.com/product_images/w/997/Almondina_Cookies_Original_4oz__12487_thumb.jpg",
    "https://loshusansupermarket.com/product_images/l/110/Cake_Loaf_Orange__92601_thumb.jpg",
    "https://loshusansupermarket.com/product_images/b/189/Bauducco_Choco_Biscuit_80g__96531_thumb.jpg",
    "https://loshusansupermarket.com/product_images/m/367/Bauducco_Butter_Cookies_340g_12oz_1_tagged__48993_thumb.jpg",
    "https://loshusansupermarket.com/product_images/u/039/Bauducco_Duo_Cake_Bar_Chocolate_27g__50587_thumb.jpg",
    "https://loshusansupermarket.com/product_images/g/364/Bauducco_Duo_Cake_Bar_Vanilla_27g__63290_thumb.jpg",
    "https://loshusansupermarket.com/product_images/u/433/Bauducco_Mini_Panettone_3.5oz__42856_thumb.jpg",
    "https://loshusansupermarket.com/product_images/c/617/Bauducco_Toast_Bites_Garlic_Parsley_120g__38078_thumb.jpg",
    "https://loshusansupermarket.com/product_images/f/271/Bauducco_Wafer_Strawberry_1.41oz__99175_thumb.jpg",
    "https://loshusansupermarket.com/product_images/x/755/Bauducco_Wafer_Chocolate_5oz__67831_thumb.jpg",
    "https://loshusansupermarket.com/product_images/t/logo%20bauducco__47400.jpg",
    "https://loshusansupermarket.com/product_images/i/511/Bauducco_Wafer_Coconut_165g__50215_thumb.jpg",
    "https://loshusansupermarket.com/product_images/v/893/Bauducco_Coconut_Wafer_165g__52386_thumb.jpg",
    "https://loshusansupermarket.com/product_images/h/916/Bauducco_Wafer_Hazelnut_165g__87207_thumb.jpg"
]

os.makedirs('product_images', exist_ok=True)

for url in urls:
    filename = os.path.join('product_images', url.split('/')[-1])
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    print(f"Downloaded: {filename}")