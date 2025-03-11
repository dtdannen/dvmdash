import Link from 'next/link'

export default function Home() {
  return (
    <div className="space-y-6">
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Admin Dashboard</h2>
        <p className="text-gray-600 mb-4">
          Welcome to the DVMDash Admin Dashboard. This interface allows you to manage and monitor your DVMDash instance.
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
          <Link href="/admin/relays" className="block p-6 bg-blue-50 rounded-lg border border-blue-100 hover:bg-blue-100 transition">
            <h3 className="font-medium text-lg text-blue-800">Relay Management</h3>
            <p className="text-blue-600 mt-2">Configure and monitor relay connections</p>
          </Link>
          
          <div className="block p-6 bg-gray-50 rounded-lg border border-gray-200">
            <h3 className="font-medium text-lg text-gray-500">System Status</h3>
            <p className="text-gray-400 mt-2">Monitor system health and performance (Coming soon)</p>
          </div>
          
          <div className="block p-6 bg-gray-50 rounded-lg border border-gray-200">
            <h3 className="font-medium text-lg text-gray-500">Configuration</h3>
            <p className="text-gray-400 mt-2">Manage system configuration (Coming soon)</p>
          </div>
        </div>
      </div>
      
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Connection Status</h2>
        <div className="space-y-2">
          <div className="flex items-center">
            <div className="w-3 h-3 rounded-full bg-green-500 mr-2"></div>
            <span>Redis: Connected</span>
          </div>
          <div className="flex items-center">
            <div className="w-3 h-3 rounded-full bg-green-500 mr-2"></div>
            <span>Postgres: Connected</span>
          </div>
        </div>
      </div>
    </div>
  )
}
