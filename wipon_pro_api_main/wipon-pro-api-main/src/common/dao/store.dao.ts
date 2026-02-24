import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  JoinColumn,
  OneToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { StoreTypeDao } from './store-type.dao';
import { DgdDao } from './dgd.dao';
import { UgdDao } from './ugd.dao';
import { UserDao } from './user.dao';

@Entity('stores')
export class StoreDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  user_id: number;

  @Column()
  region_id: number;

  @Column()
  city: string;

  @Column()
  buisness_store_name: string;

  @Column({
    type: 'varchar',
    length: 12,
  })
  buisness_bin: string;

  @Column()
  license_number: string;

  @Column({
    type: 'integer',
    default: 100,
  })
  radius: number;

  @Column()
  street: string;

  @Column()
  house: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @DeleteDateColumn()
  deleted_at: Date;

  @Column()
  buisness_store_type_id: number;

  @Column()
  is_exported: boolean;

  @Column()
  buisness_store_address: string;

  @Column()
  payer_postal_address: string;

  @Column()
  buisness_full_legal_name: string;

  @Column()
  buisness_dgd_id: string;

  @Column()
  buisness_ugd_id: string;

  @Column()
  payer_email: string;

  @Column()
  ugd_license_id: number;

  @Column()
  license_remapping_at: Date;

  @Column()
  fin_user_id: number;

  @Column()
  payer_bin: string;

  @Column()
  payer_address: string;

  @Column()
  payer_name: string;

  @OneToOne(() => StoreTypeDao, (storeType) => storeType.store)
  @JoinColumn({ name: 'buisness_store_type_id' })
  buisnessStoreType: StoreTypeDao;

  @OneToOne(() => DgdDao, (dgd) => dgd.store)
  @JoinColumn({ name: 'buisness_dgd_id' })
  dgd: DgdDao;

  @OneToOne(() => UgdDao, (ugd) => ugd.store)
  @JoinColumn({ name: 'buisness_ugd_id' })
  ugd: UgdDao;

  @OneToOne(() => UserDao, (user) => user.store)
  @JoinColumn({ name: 'user_id' })
  user: UserDao;
}
