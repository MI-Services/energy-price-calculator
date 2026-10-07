#!/usr/bin/env python3
"""Validatie-hulp: rangschik de dagprijzen en toon rank/tijd/prijs.

Kopieer de "hours" uit de server-API (of HA-attributen) in PRICES hieronder
en draai:  python3 validate_prices.py

Output: gesorteerd op laagste consumer_price, met rank (1 = goedkoopste),
de lokale tijd van het interval en de prijs. Vergelijk dit met wat de
HA-sensoren tonen: sensor.uurprijs_<hh>_00 moet dezelfde prijs dragen en
binary_sensor.goedkoopste_<pct>_van_de_dag moet aan staan als
rank/24*100 <= pct (uurdiensten; bij kwartieren geldt rank/96).
"""

HOURS_PER_DAY = 24  # kwartiertarieven: 96

PRICES = [
    {"hour": 22, "consumer_price": 0.3731156},
    {"hour": 23, "consumer_price": 0.36608549999999995},
    {"hour": 0, "consumer_price": 0.3585835},
    {"hour": 1, "consumer_price": 0.354288},
    {"hour": 2, "consumer_price": 0.351021},
    {"hour": 3, "consumer_price": 0.35514710000000005},
    {"hour": 4, "consumer_price": 0.36521430000000005},
    {"hour": 5, "consumer_price": 0.3732729},
    {"hour": 6, "consumer_price": 0.363363},
    {"hour": 7, "consumer_price": 0.35488090000000005},
    {"hour": 8, "consumer_price": 0.31881079999999995},
    {"hour": 9, "consumer_price": 0.2763034999999999},
    {"hour": 10, "consumer_price": 0.2403302},
    {"hour": 11, "consumer_price": 0.20324369999999997},
    {"hour": 12, "consumer_price": 0.20693419999999996},
    {"hour": 13, "consumer_price": 0.24636809999999998},
    {"hour": 14, "consumer_price": 0.31665699999999997},
    {"hour": 15, "consumer_price": 0.3747733},
    {"hour": 16, "consumer_price": 0.4076974},
    {"hour": 17, "consumer_price": 0.42634350000000004},
    {"hour": 18, "consumer_price": 0.41564709999999994},
    {"hour": 19, "consumer_price": 0.3997235},
    {"hour": 20, "consumer_price": 0.39448419999999995},
    {"hour": 21, "consumer_price": 0.3726316},
]

PCT_THRESHOLDS = [10, 20, 30, 40, 50, 60, 70, 80, 90]


def main():
    ranked = sorted(PRICES, key=lambda h: h["consumer_price"])
    print(f"{'rank':>4}  {'tijd':>7}  {'prijs':>8}  aan bij")
    print("-" * 40)
    for rank, hour in enumerate(ranked, start=1):
        pct = rank * 100 // HOURS_PER_DAY
        aan = [p for p in PCT_THRESHOLDS if rank * 100 <= p * HOURS_PER_DAY]
        print(f"{rank:>4}  {hour['hour']:02d}:00  {hour['consumer_price']:8.4f}  {aan}")

    print()
    duurste = ranked[-1]
    goedkoopste = ranked[0]
    print(f"Goedkoopste: {goedkoopste['hour']:02d}:00 uur ({goedkoopste['consumer_price']:.4f})")
    print(f"Duurste:     {duurste['hour']:02d}:00 uur ({duurste['consumer_price']:.4f})")
    print(f"Verschil:    {(duurste['consumer_price'] - goedkoopste['consumer_price']) * 100:.1f} ct/kWh")


if __name__ == "__main__":
    main()
