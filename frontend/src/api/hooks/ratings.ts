import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { ratingKeys, userKeys } from '../keys'
import type { PendingRating, Rating, RatingCreate, RoleRated } from '../types'

/** Ratings the caller still owes, which drives the post-ride prompt. */
export function usePendingRatings() {
  return useQuery({
    queryKey: ratingKeys.pending,
    queryFn: ({ signal }) => api.get<PendingRating[]>('/ratings/pending', undefined, signal),
  })
}

/** Ratings received by one user, newest first (openapi: listUserRatings). */
export function useUserRatings(userId: number | undefined, roleRated?: RoleRated) {
  return useQuery({
    queryKey: ratingKeys.byUser(userId ?? 0, roleRated),
    queryFn: ({ signal }) =>
      api.get<Rating[]>(`/users/${userId}/ratings`, { role_rated: roleRated }, signal),
    enabled: userId !== undefined,
  })
}

export function useCreateRating() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RatingCreate) => api.post<Rating>('/ratings', body),
    onSuccess: (rating) => {
      // Clears the pending prompt and refreshes the ratee's cached average,
      // wherever it is shown (public profile, PersonLine on a shared ride).
      void queryClient.invalidateQueries({ queryKey: ratingKeys.all })
      void queryClient.invalidateQueries({ queryKey: userKeys.detail(rating.to_user_id) })
    },
  })
}
