import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
  ManyToOne,
  JoinColumn,
} from 'typeorm';
import { UserDao } from './user.dao';

@Entity('devices')
export class DeviceDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ nullable: true })
  user_id: number | null;

  @Column()
  device_code: string;

  @Column()
  application_type: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @ManyToOne(() => UserDao, (user) => user.devices)
  @JoinColumn({ name: 'user_id' })
  user: UserDao;
}
