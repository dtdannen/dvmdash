export function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="relative">
        <div className="w-16 h-16 border-4 border-gray-700 border-t-purple-500 rounded-full animate-spin"></div>
        <div className="mt-4 text-center text-gray-400">{message}</div>
      </div>
    </div>
  )
}
