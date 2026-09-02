import {CanonEntityDetail} from "../../../features/canon/CanonEntityDetail";

export default async function CanonEntityPage({params}: {params: Promise<{entityId: string}>}) {
  const {entityId} = await params;
  return <CanonEntityDetail entityId={entityId} />;
}
