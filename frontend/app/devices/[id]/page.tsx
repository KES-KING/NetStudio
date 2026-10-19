import DeviceDetail from "../../../components/DeviceDetail";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DeviceDetail key={id} id={id} />;
}
