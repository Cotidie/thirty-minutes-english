/** The amount `text` asks to gift, when it is a whole number from 1 to `balance`; spaces around it are fine. */
export function giftable(text: string, balance: number): number | null {
  const digits = text.trim()
  if (!/^\d+$/.test(digits)) return null
  const amount = Number(digits)
  return amount >= 1 && amount <= balance ? amount : null
}

/** "1 credit", "200 credits". */
export function creditCount(amount: number): string {
  return amount === 1 ? '1 credit' : `${amount} credits`
}
