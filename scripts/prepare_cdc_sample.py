import pandas as pd
df = pd.read_csv('data/samples/U.S._Chronic_Disease_Indicators.csv')
print(f'Full dataset: {df.shape[0]} rows × {df.shape[1]} cols')
print(f'Columns: {list(df.columns)}')
print(f'Dtypes:\n{df.dtypes}')

# Simple random sample, seed 42 (deterministic)
sample = df.sample(n=50000, random_state=42)
sample.to_csv('data/samples/chronic_disease_50K.csv', index=False)
print(f'\nSample saved: {sample.shape[0]} rows')
print(f'File size: {sample.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB (in memory)')


