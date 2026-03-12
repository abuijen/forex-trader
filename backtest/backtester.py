def backtest(df):
    wins = 0
    losses = 0
    for i in range(1,len(df)-1):
        if df["close"][i+1] > df["close"][i]:
            wins += 1
        else:
            losses += 1
    winrate = wins / (wins + losses)
    return winrate