import { Fragment } from 'react'
import { Link } from 'react-router-dom'

/** Links to the sessions by id, comma separated. */
export function SessionLinks({ ids }: { ids: number[] }) {
  return (
    <>
      {ids.map((id, i) => (
        <Fragment key={id}>
          {i > 0 && ', '}
          <Link to={`/s/${id}`}>Session {id}</Link>
        </Fragment>
      ))}
    </>
  )
}
