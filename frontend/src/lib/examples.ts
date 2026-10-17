import type { AccessPolicy } from './types'

export interface QueryExample {
  id: string
  title: string
  query: string
  restricted?: string[]
}

/** Verified examples on the concert_singer example database, one per error class. */
export const EXAMPLE_DB = 'concert_singer'

export const QUERY_EXAMPLES: QueryExample[] = [
  { id: 'multi', title: 'Several errors at once', query: "SELEC Name, count(*) FORM singr WHERE Age > 'thirty'" },
  { id: 'correct', title: 'Correct query', query: 'SELECT Name, Country FROM singer WHERE Age > 40 ORDER BY Age DESC' },
  { id: 'syntax', title: 'Syntax error', query: 'SELECT Name, Country FORM singer WHERE Age > 40' },
  { id: 'table', title: 'Unknown table', query: "SELECT count(*) FROM singers WHERE Country = 'France'" },
  { id: 'column', title: 'Unknown column', query: 'SELECT Nmae, Age FROM singer ORDER BY Age' },
  { id: 'type', title: 'Type mismatch', query: "SELECT Name FROM singer WHERE Age > 'thirty'" },
  {
    id: 'ambiguous',
    title: 'Ambiguous column',
    query: 'SELECT Singer_ID, Name FROM singer JOIN singer_in_concert ON singer.Singer_ID = singer_in_concert.Singer_ID',
  },
  { id: 'aggregate', title: 'Aggregate in WHERE', query: 'SELECT Name FROM singer WHERE Age > avg(Age)' },
  {
    id: 'join',
    title: 'Missing join condition',
    query: 'SELECT T2.concert_Name FROM stadium AS T1 JOIN concert AS T2 WHERE T1.Capacity > 5000',
  },
  { id: 'permission', title: 'Restricted table (stadium)', query: 'SELECT Name, Capacity FROM stadium', restricted: ['stadium'] },
]

export const QUESTION_EXAMPLES: Record<string, string[]> = {
  concert_singer: [
    'How many singers are older than 30?',
    'What is the average age of singers from France?',
    'Which stadium has the largest capacity?',
    'List the names of singers who performed in a concert in 2014.',
  ],
  default: ['How many rows are in the largest table?', 'List the first 10 records ordered by name.'],
}

export const emptyPolicy = (): AccessPolicy => ({ restricted_tables: [], restricted_columns: [] })
