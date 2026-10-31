/** What pressing a button costs, beside its name and out of it; nothing for whoever is not charged. */
export function Price({ amount }: { amount: number }) {
  if (amount <= 0) return null
  return (
    <span className="btn-price" aria-hidden="true">
      {amount}
    </span>
  )
}
