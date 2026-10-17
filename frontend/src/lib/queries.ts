import { useQuery } from '@tanstack/react-query'
import { api } from './api'

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15_000, retry: 0, staleTime: 5_000 })

export const useDatabases = () => useQuery({ queryKey: ['databases'], queryFn: api.databases, staleTime: 5 * 60_000 })

export const useSavedSchemas = () => useQuery({ queryKey: ['saved-schemas'], queryFn: api.savedSchemas })

export const useLabels = () => useQuery({ queryKey: ['labels'], queryFn: api.labels, staleTime: Infinity })
