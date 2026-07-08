-- Owner-only rotation of a class join code. The JS client cannot call gen_join_code()
-- inside an UPDATE value, so this SECURITY DEFINER RPC does it server-side, guarded by
-- is_class_owner(), reusing the collision-safe generator from 0001.
create function rotate_join_code(p_class uuid) returns text
  language plpgsql security definer set search_path = public as $$
declare v_code text;
begin
  if not is_class_owner(p_class) then
    raise exception 'not the class owner' using errcode = 'insufficient_privilege';
  end if;
  v_code := gen_join_code();
  update classes set join_code = v_code where id = p_class;
  return v_code;
end;
$$;

revoke all on function rotate_join_code(uuid) from public;
grant execute on function rotate_join_code(uuid) to authenticated;
